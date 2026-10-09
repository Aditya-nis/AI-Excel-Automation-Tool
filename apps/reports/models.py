from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class ReportDefinition(models.Model):
    REPORT_TYPES = [
        ('sales_mis', 'Sales Performance MIS'),
        ('finance_mis', 'Financial & Revenue MIS'),
        ('inventory_mis', 'Inventory & Stock MIS'),
        ('operations_mis', 'Operations & Workflow MIS'),
        ('hr_mis', 'Human Resources & Attendance MIS'),
        ('custom_mis', 'Custom Governed MIS Report'),
    ]

    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='report_definitions')
    name = models.CharField(max_length=255)
    report_type = models.CharField(max_length=32, choices=REPORT_TYPES, default='custom_mis')
    description = models.TextField(blank=True)
    dataset = models.ForeignKey('datasets.Dataset', on_delete=models.CASCADE, related_name='report_definitions')
    semantic_model = models.ForeignKey('semantic_model.SemanticModel', on_delete=models.SET_NULL, null=True, blank=True)
    date_column = models.CharField(max_length=255, blank=True)
    metric_columns = models.JSONField(default=list, blank=True)
    dimension_columns = models.JSONField(default=list, blank=True)
    filters_config = models.JSONField(default=dict, blank=True)
    version_number = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = ('workspace', 'name')

    def __str__(self):
        return f"{self.name} ({self.get_report_type_display()})"

class ReportRun(models.Model):
    report_definition = models.ForeignKey(ReportDefinition, on_delete=models.CASCADE, related_name='runs')
    dataset_version = models.ForeignKey('datasets.DatasetVersion', on_delete=models.CASCADE, related_name='report_runs')
    parameters_applied = models.JSONField(default=dict, blank=True)
    summary_kpis = models.JSONField(default=dict, blank=True)
    table_data = models.JSONField(default=dict, blank=True)
    chart_payloads = models.JSONField(default=dict, blank=True)
    excel_export_path = models.CharField(max_length=512, blank=True)
    pdf_export_path = models.CharField(max_length=512, blank=True)
    csv_export_path = models.CharField(max_length=512, blank=True)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-generated_at']

    def __str__(self):
        return f"Report Run: {self.report_definition.name} ({self.generated_at.strftime('%Y-%m-%d %H:%M')})"
