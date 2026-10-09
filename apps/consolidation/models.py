from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class ConsolidationRun(models.Model):
    OP_CHOICES = [
        ('append', 'Append / Union Tables'),
        ('join', 'Join / Merge Tables'),
    ]

    JOIN_TYPE_CHOICES = [
        ('left', 'Left Outer Join'),
        ('inner', 'Inner Join'),
        ('right', 'Right Outer Join'),
        ('outer', 'Full Outer Join'),
    ]

    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='consolidations')
    operation_type = models.CharField(max_length=20, choices=OP_CHOICES)
    primary_dataset = models.ForeignKey('datasets.Dataset', on_delete=models.CASCADE, related_name='primary_consolidations')
    secondary_dataset = models.ForeignKey('datasets.Dataset', on_delete=models.CASCADE, related_name='secondary_consolidations')
    resulting_dataset = models.ForeignKey('datasets.Dataset', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_by_consolidation')
    join_type = models.CharField(max_length=20, choices=JOIN_TYPE_CHOICES, blank=True, default='left')
    join_keys = models.JSONField(default=dict, blank=True)
    column_mappings = models.JSONField(default=dict, blank=True)
    cardinality_preview = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, default='completed')
    records_produced = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.operation_type.title()}: {self.primary_dataset.name} + {self.secondary_dataset.name}"

class ReconciliationRun(models.Model):
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='reconciliations')
    name = models.CharField(max_length=255)
    primary_dataset = models.ForeignKey('datasets.Dataset', on_delete=models.CASCADE, related_name='primary_reconciliations')
    secondary_dataset = models.ForeignKey('datasets.Dataset', on_delete=models.CASCADE, related_name='secondary_reconciliations')
    matching_keys = models.JSONField(default=dict)
    matched_records_count = models.PositiveIntegerField(default=0)
    unmatched_primary_count = models.PositiveIntegerField(default=0)
    unmatched_secondary_count = models.PositiveIntegerField(default=0)
    control_total_field_1 = models.CharField(max_length=255, blank=True)
    control_total_field_2 = models.CharField(max_length=255, blank=True)
    control_total_sum_1 = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    control_total_sum_2 = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    variance = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    tolerance = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    is_reconciled = models.BooleanField(default=False)
    report_summary = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Reconciliation: {self.name} (Variance: {self.variance})"
