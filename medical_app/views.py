
# -*- coding: utf-8 -*-

from django.shortcuts import render

# Create your views here.
import json
import feedparser
import numpy as np
import pandas as pd
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from .models import MedicalRecord, UserInteraction
from sklearn.cluster import KMeans
from sentence_transformers import SentenceTransformer

line_bot_api = LineBotApi(settings.LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(settings.LINE_CHANNEL_SECRET)

# 載入訓練好的模型
sentence_transformer = SentenceTransformer('trained_model')
#kmeans = KMeans()  # 載入你預先訓練好的KMeans模型

# 1. 讀取 CSV 資料集
file_path = 'kmtd.csv'  # 替換為你的 CSV 路徑
df = pd.read_csv(file_path)
sentences = df['text'].tolist()

# 定義大項目科別
departments = ['內科', '外科', '泌尿科', '婦產科', '耳鼻喉科', '眼科', '牙科']

# 定義常用症狀
symptoms = {
    '內科': ['頭痛', '咳嗽', '發燒', '呼吸困難', '呼吸不順', '心悸', '氣喘', '便秘', '噁心', '嘔吐', '失眠', '癲癇', '胸痛', '胸悶'],
    '外科': ['外傷', '吞嚥困難', '乳房疼痛', '坐骨神經痛', '脊椎側彎'],
    '泌尿科': ['頻尿', '解尿疼痛', '排尿困難', '單側腰痛', '血尿', '夜尿'],
    '婦產科': ['月經不規則', '尿失禁', '經痛', '頻尿', '性傳染病'],
    '耳鼻喉科': ['耳鳴', '鼻塞', '流鼻血', '吞嚥困難', '咳嗽', '頭痛', '發燒'],
    '眼科': ['視力模糊', '眼睛紅腫', '乾眼症', '急性視力喪失', '眼睛痛'],
    '牙科': ['牙齒疼痛', '牙齦出血', '蛀牙', '牙齦腫大', '牙齦化膿', '口臭'],
}

# 定義細項目科別
sub_departments = {
    '內科': ['一般內科', '神經科', '胸腔科', '腎臟科', '心臟科', '肝膽腸胃科', '內分泌科'],
    '外科': ['一般外科', '骨科', '乳房外科', '皮膚科', '神經外科'],
}

# 使用訓練集進行大科別分群    
kmeans = KMeans(n_clusters = len(departments), init = 'k-means++', random_state = 42)
kmeans = kmeans.fit(sentence_transformer.encode(sentences))

@csrf_exempt
def callback(request):
    if request.method == 'POST':
        signature = request.META['HTTP_X_LINE_SIGNATURE']
        body = request.body.decode('utf-8')

        try:
            handler.handle(body, signature)
        except InvalidSignatureError:
            return HttpResponse(status=403)

        return HttpResponse(status=200)
    else:
        return HttpResponse(status=405)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_input = event.message.text
    
    user_interaction, created = UserInteraction.objects.get_or_create(user_id=user_id)

    if user_input == "@附近醫療機構":
        google_maps_url = "https://www.google.com/maps/search/?api=1&query=hospitals&query"
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text=f"請點擊以下連結來查看附近的醫療機構：\n{google_maps_url}")
        )
    elif user_input == "@衛生署公告":
        feed_url = "https://www.mohw.gov.tw/rss-16-1.html"
        feed = feedparser.parse(feed_url)
        announcements = []
        for entry in feed.entries[:5]:  # 只取前5則公告
            title = entry.title
            link = entry.link
            announcements.append(f"{title}\n{link}")
        announcement_text = "\n\n".join(announcements)
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text=announcement_text)
        )
    else:
        # 將症狀描述存到資料庫
        record = MedicalRecord(user_id=user_id, symptom_description=user_input)
        record.save()
        
        if user_input not in ['1','2','3','4']:
            response = handle_first_clustering(user_input, user_interaction) # 第一次輸入    
        else:
            response = handle_second_clustering(user_input, user_interaction) # 第二次輸入

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=json.dumps(response.content.decode('utf-8'))))

        # 回復用戶
        #line_bot_api.reply_message(
        #    event.reply_token,
        #    TextSendMessage(text='您的症状已經存入資料庫，謝謝！')
        #)

def index(request):
    return render(request, 'index.html')

def handle_first_clustering(user_input, user_interaction):
    """ 處理第一次分群 """
    vectorized_input = vectorize_input(user_input)
    (first_cluster_label, second_cluster_label), confidence_first = cluster_input(vectorized_input)

    first_cluster_result = departments[first_cluster_label]
    
    # 保存分群結果到 database
    user_interaction.first_cluster_label = first_cluster_label
    user_interaction.second_cluster_label = second_cluster_label
    user_interaction.user_input = user_input
    user_interaction.save()

    if confidence_first >= 0.8 and first_cluster_result in sub_departments:
        return refine_clustering(vectorized_input, first_cluster_result)
    elif confidence_first >= 0.8:
        return JsonResponse({'建議掛號科別：': first_cluster_result})
    else:
        first_symptom = symptoms[first_cluster_result][round]
        second_symptoms = symptoms[second_cluster_label][round:2]
        
        # 保存症狀到 database
        user_interaction.symptoms = {
            '1': first_symptom,
            '2': second_symptoms[0],
            '3': second_symptoms[1],
            '4': '以上皆非'
        }
        user_interaction.save()
        
        return JsonResponse({
            '請問是否有以下症狀：': {
                '1': first_symptom,
                '2': second_symptoms[0],
                '3': second_symptoms[1],
                '4': '以上皆非'
            }
        })
 
def handle_second_clustering(user_choice, user_interaction):
    """ 處理使用者的第二次輸入以調整分類結果 """
    first_cluster_label = user_interaction.first_cluster_label
    second_cluster_label = user_interaction.second_cluster_label
    user_input = user_interaction.user_input
    
    if user_choice == '1':
        if departments[first_cluster_label] in sub_departments:
            return refine_clustering(vectorize_input(user_input), departments[first_cluster_label])
        else:
            return JsonResponse({'建議掛號科別：': departments[first_cluster_label]})

    elif user_choice in ['2', '3']:
        # 提高第二名科別的權重
        adjusted_weights = np.zeros(len(departments))
        adjusted_weights[second_cluster_label] = 1.5  # 調整權重
        vectorized_input = vectorize_input(user_input + user_interaction.symptoms[user_choice])
        second_cluster_label = kmeans.predict(vectorized_input, sample_weight=adjusted_weights)

        if departments[second_cluster_label] in sub_departments:
            return refine_clustering(vectorized_input, departments[second_cluster_label])
        else:
            return JsonResponse({'建議掛號科別：': departments[second_cluster_label]})

    elif user_choice == '4':
        # 降低第一名與第二名的權重
        adjusted_weights = np.ones(len(departments)) * 0.5
        adjusted_weights[first_cluster_label] = 0.5
        adjusted_weights[second_cluster_label] = 0.5
        vectorized_input = vectorize_input(user_input + user_interaction.symptoms[user_choice])
        second_cluster_label = kmeans.predict(vectorized_input, sample_weight=adjusted_weights)

        if departments[second_cluster_label] in sub_departments:
            return refine_clustering(vectorized_input, departments[second_cluster_label])
        else:
            return JsonResponse({'建議掛號科別：': departments[second_cluster_label]})     

def refine_clustering(vectorized_input, main_department):
    """ 如有需要，進行細科別分群 """
    sub_kmeans = KMeans(n_clusters=len(sub_departments[main_department]), init='k-means++', random_state=42)
    sub_sentences = [sentences[i] for i in range(len(sentences)) if kmeans.labels_[i] == departments.index(main_department)]
    sub_kmeans.fit(sentence_transformer.encode(sub_sentences))
    sub_cluster_label = sub_kmeans.predict(vectorized_input)
    return JsonResponse({'建議掛號科別：': sub_departments[main_department][sub_cluster_label[0]]})


def vectorize_input(user_input):
    """ 使用訓練好的 SentenceTransformer 模型對使用者的輸入進行向量化 """
    return sentence_transformer.encode([user_input])

def cluster_input(vectorized_input):
    """ 使用訓練好的 KMeans 模型對使用者的輸入進行分群 """

    # 計算該向量與所有群集中心之間的距離
    distances = kmeans.transform(vectorized_input)

    # 找出前兩個最近的群集
    closest_clusters = distances.argsort(axis=1)[:, :2]

    # 計算對應的"信心值"（用距離的反比表示）
    confidence_first = 1 / (distances[0][closest_clusters[0][0]] + 1e-6)  # 加1e-6避免除以零

    # 返回最接近的群集標籤，與對應的信心值
    return (closest_clusters[0][0], closest_clusters[0][1]), confidence_first