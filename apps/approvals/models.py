from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class ApprovalRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    TYPE_CHOICES = [
        ('report_publication', 'MIS Report Publication'),
        ('schema_change', 'Schema Drift / Modification'),
        ('workflow_automation', 'Automated Workflow Execution'),
        ('recipe_change', 'Cleaning Recipe Modification'),
    ]

    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='approvals')
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name='requested_approvals')
    request_type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    target_object_type = models.CharField(max_length=64, blank=True)
    target_object_id = models.CharField(max_length=128, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_approvals')
    review_comments = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.status.upper()}] {self.title} by {self.requester.username}"
