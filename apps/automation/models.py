from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class WorkflowSchedule(models.Model):
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='workflows')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    dataset = models.ForeignKey('datasets.Dataset', on_delete=models.CASCADE, related_name='workflows')
    cleaning_recipe = models.ForeignKey('cleaning.CleaningRecipe', on_delete=models.CASCADE, related_name='workflows')
    report_definition = models.ForeignKey('reports.ReportDefinition', on_delete=models.SET_NULL, null=True, blank=True)
    cron_expression = models.CharField(max_length=64, default='0 6 1 * *')  # 1st of every month
    timezone_name = models.CharField(max_length=64, default='UTC')
    is_active = models.BooleanField(default=True)
    dry_run_mode = models.BooleanField(default=False)
    stop_on_drift = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = ('workspace', 'name')

    def __str__(self):
        return f"{self.name} ({self.cron_expression})"

class JobRun(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('drift_detected', 'Halted: Schema Drift Detected'),
        ('failed', 'Failed'),
    ]

    workflow = models.ForeignKey(WorkflowSchedule, on_delete=models.CASCADE, related_name='job_runs')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='queued')
    trigger_type = models.CharField(max_length=32, default='manual')
    schema_drift_detected = models.BooleanField(default=False)
    drift_details = models.JSONField(default=dict, blank=True)
    execution_logs = models.TextField(blank=True)
    source_file = models.ForeignKey('datasets.SourceFile', on_delete=models.SET_NULL, null=True, blank=True)
    output_version = models.ForeignKey('datasets.DatasetVersion', on_delete=models.SET_NULL, null=True, blank=True)
    report_run = models.ForeignKey('reports.ReportRun', on_delete=models.SET_NULL, null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(default=0.0)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Job #{self.id} for {self.workflow.name} ({self.status})"
