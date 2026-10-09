from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class TransformationRun(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('rolled_back', 'Rolled Back'),
    ]

    dataset = models.ForeignKey('datasets.Dataset', on_delete=models.CASCADE, related_name='transformation_runs')
    source_version = models.ForeignKey('datasets.DatasetVersion', on_delete=models.CASCADE, related_name='runs_from_version')
    target_version = models.ForeignKey('datasets.DatasetVersion', on_delete=models.SET_NULL, null=True, blank=True, related_name='runs_to_version')
    run_type = models.CharField(max_length=32, default='manual')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    steps_count = models.PositiveIntegerField(default=0)
    rows_before = models.PositiveIntegerField(default=0)
    rows_after = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Run #{self.id} on {self.dataset.name} ({self.status})"

class TransformationStep(models.Model):
    OPERATION_CHOICES = [
        ('trim_whitespace', 'Trim Whitespace'),
        ('change_case', 'Standardize Text Case'),
        ('normalize_date', 'Normalize Dates'),
        ('convert_type', 'Convert Column Type'),
        ('remove_duplicates', 'Remove Duplicate Rows'),
        ('fill_missing', 'Fill Missing Values'),
        ('drop_missing', 'Drop Rows with Missing Values'),
        ('map_categories', 'Map Inconsistent Categories'),
        ('filter_rows', 'Filter Records by Condition'),
        ('handle_outliers', 'Handle Outliers'),
    ]

    run = models.ForeignKey(TransformationRun, on_delete=models.CASCADE, related_name='steps')
    step_number = models.PositiveIntegerField()
    operation_type = models.CharField(max_length=50, choices=OPERATION_CHOICES)
    column_name = models.CharField(max_length=255, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    affected_rows = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['step_number']

    def __str__(self):
        return f"Step {self.step_number}: {self.operation_type} on {self.column_name or 'table'}"

class CleaningRecipe(models.Model):
    """Reusable cleaning rule recipes for monthly / periodic automated execution."""
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='cleaning_recipes')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    target_schema = models.JSONField(default=dict, blank=True)
    steps_config = models.JSONField(default=list, blank=True)
    version_number = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = ('workspace', 'name')

    def __str__(self):
        return f"{self.name} v{self.version_number} ({self.workspace.name})"
