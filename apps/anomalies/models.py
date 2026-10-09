from django.db import models

class AnomalyEvent(models.Model):
    SEVERITY_CHOICES = [
        ('critical', 'Critical Outlier / Extreme Spike'),
        ('warning', 'Warning / Noticeable Deviation'),
        ('info', 'Informational / Low Variance'),
    ]

    STATUS_CHOICES = [
        ('open', 'Open / Needs Attention'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
    ]

    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='anomalies')
    dataset = models.ForeignKey('datasets.Dataset', on_delete=models.CASCADE, related_name='anomalies')
    metric_name = models.CharField(max_length=255)
    observed_value = models.FloatField()
    baseline_value = models.FloatField()
    deviation_percent = models.FloatField(default=0.0)
    z_score = models.FloatField(default=0.0)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='warning')
    detection_method = models.CharField(max_length=64, default='statistical_zscore')
    evidence = models.TextField()
    period_label = models.CharField(max_length=128, blank=True)
    review_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-detected_at']

    def __str__(self):
        return f"[{self.severity.upper()}] {self.metric_name}: {self.deviation_percent}% deviation ({self.dataset.name})"

class MetricForecast(models.Model):
    dataset = models.ForeignKey('datasets.Dataset', on_delete=models.CASCADE, related_name='forecasts')
    metric_name = models.CharField(max_length=255)
    date_column = models.CharField(max_length=255)
    method = models.CharField(max_length=64, default='linear_trend')
    historical_points = models.PositiveIntegerField(default=0)
    horizon_periods = models.PositiveIntegerField(default=3)
    forecast_results = models.JSONField(default=list)
    mae_error = models.FloatField(null=True, blank=True)
    assumptions = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Forecast: {self.metric_name} ({self.dataset.name})"
