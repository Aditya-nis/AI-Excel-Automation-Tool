from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class ChatSession(models.Model):
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='chat_sessions')
    dataset = models.ForeignKey('datasets.Dataset', on_delete=models.CASCADE, related_name='chat_sessions')
    semantic_model = models.ForeignKey('semantic_model.SemanticModel', on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=255, default='New Analytical Session')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.title} ({self.dataset.name})"

class QueryRun(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='queries')
    user_query = models.TextField()
    parsed_intent = models.JSONField(default=dict, blank=True)
    generated_query_plan = models.JSONField(default=dict, blank=True)
    result_data = models.JSONField(default=dict, blank=True)
    caveats = models.JSONField(default=list, blank=True)
    confidence_score = models.FloatField(default=1.0)
    execution_time_ms = models.FloatField(default=0.0)
    recommended_chart = models.CharField(max_length=32, default='table')
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Q: {self.user_query[:50]}... ({self.session.id})"
