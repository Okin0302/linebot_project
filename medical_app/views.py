
# -*- coding: utf-8 -*-

from django.shortcuts import render

# Create your views here.
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from .models import MedicalRecord
import json
from django.conf import settings
import feedparser

line_bot_api = LineBotApi(settings.LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(settings.LINE_CHANNEL_SECRET)

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
    res_text = event.message.text

    if res_text == "@附近醫療機構":
        google_maps_url = "https://www.google.com/maps/search/?api=1&query=hospitals&query"
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text=f"請點擊以下連結來查看附近的醫療機構：\n{google_maps_url}")
        )
    elif res_text == "@衛生署公告":
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
        record = MedicalRecord(user_id=user_id, symptom_description=res_text)
        record.save()

        # 回復用戶
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='您的症状已經存入資料庫，謝謝！')
        )

def index(request):
    return render(request, 'index.html')
