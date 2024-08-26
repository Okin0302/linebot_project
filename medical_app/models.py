from django.db import models

# Create your models here.

class MedicalRecord(models.Model):
    user_id = models.CharField(max_length=255)
    symptom_description = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # return self.symptom_description
        return f"{self.user_id}:{self.symptom_description}"
