from django.db import models

class DataQualityIssue(models.Model):
    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('warning', 'Warning'),
        ('info', 'Informational'),
    ]

    ISSUE_TYPE_CHOICES = [
        ('missing_values', 'Missing Values'),
        ('duplicate_rows', 'Duplicate Rows'),
        ('invalid_date', 'Invalid / Unparseable Dates'),
        ('invalid_numeric', 'Invalid Numeric Format'),
        ('outlier', 'Statistical Outlier (3+ Std Dev / IQR)'),
        ('inconsistent_casing', 'Inconsistent Text Whitespace / Casing'),
        ('category_variation', 'Fuzzy Category Variations'),
        ('broken_rule', 'Broken Business Rule'),
    ]

    version = models.ForeignKey('datasets.DatasetVersion', on_delete=models.CASCADE, related_name='quality_issues')
    column_name = models.CharField(max_length=255, blank=True)
    issue_type = models.CharField(max_length=50, choices=ISSUE_TYPE_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='warning')
    affected_row_count = models.PositiveIntegerField(default=0)
    evidence_summary = models.TextField()
    sample_row_indices = models.JSONField(default=list, blank=True)
    suggested_action = models.CharField(max_length=64, blank=True)
    suggested_params = models.JSONField(default=dict, blank=True)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-severity', '-affected_row_count']

    def __str__(self):
        return f"{self.get_issue_type_display()} on {self.column_name or 'dataset'} ({self.affected_row_count} rows)"

class DataQualityReport(models.Model):
    version = models.OneToOneField('datasets.DatasetVersion', on_delete=models.CASCADE, related_name='quality_report')
    overall_score = models.FloatField(default=100.0)
    completeness_score = models.FloatField(default=100.0)
    uniqueness_score = models.FloatField(default=100.0)
    validity_score = models.FloatField(default=100.0)
    consistency_score = models.FloatField(default=100.0)
    scoring_formula = models.TextField(default="Score = 100 - (missing_pen + dup_pen + invalid_pen + outlier_pen)")
    total_issues_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Quality Report for {self.version} (Score: {self.overall_score}%)"
