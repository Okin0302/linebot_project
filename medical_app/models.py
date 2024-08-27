from django.db import models

# Create your models here.

class MedicalRecord(models.Model):
    user_id = models.CharField(max_length=255)
    symptom_description = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # return self.symptom_description
        return f"{self.user_id}:{self.symptom_description}"

class UserInteraction(models.Model):
    user_id = models.CharField(max_length=255, unique=True)
    first_cluster_label = models.IntegerField(null=True, blank=True)
    second_cluster_label = models.IntegerField(null=True, blank=True)
    user_input = models.TextField(null=True, blank=True)
    symptoms = models.JSONField(null=True, blank=True)  # Use JSONField to store symptoms

    def __str__(self):
        return self.user_id
    