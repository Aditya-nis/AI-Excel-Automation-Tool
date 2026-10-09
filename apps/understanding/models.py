from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class UnderstandingAssessment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('overridden', 'User Overridden'),
    ]

    BAND_CHOICES = [
        ('high', 'High (>=0.90)'),
        ('medium', 'Medium (0.70 - 0.89)'),
        ('low', 'Low (<0.70)'),
    ]

    version = models.ForeignKey('datasets.DatasetVersion', on_delete=models.CASCADE, related_name='understanding_assessments')
    column_name = models.CharField(max_length=255)
    inferred_role = models.CharField(max_length=50)
    confidence_score = models.FloatField(default=0.0)
    confidence_band = models.CharField(max_length=20, choices=BAND_CHOICES, default='low')
    evidence = models.TextField()
    sample_patterns = models.JSONField(default=list, blank=True)
    review_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    user_override_role = models.CharField(max_length=50, blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-confidence_score']
        unique_together = ('version', 'column_name')

    def __str__(self):
        return f"{self.column_name}: {self.inferred_role} ({self.confidence_band}, {self.review_status})"
