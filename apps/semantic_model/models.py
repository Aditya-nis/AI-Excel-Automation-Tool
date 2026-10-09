from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class SemanticModel(models.Model):
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='semantic_models')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    primary_dataset = models.ForeignKey('datasets.Dataset', on_delete=models.CASCADE, related_name='semantic_models')
    is_default = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = ('workspace', 'name')

    def __str__(self):
        return f"Semantic Model: {self.name} ({self.workspace.name})"

class SemanticDimension(models.Model):
    DIMENSION_TYPE_CHOICES = [
        ('categorical', 'Categorical'),
        ('time', 'Date / Time'),
        ('geographical', 'Geographical'),
        ('identifier', 'Identifier'),
    ]

    semantic_model = models.ForeignKey(SemanticModel, on_delete=models.CASCADE, related_name='dimensions')
    name = models.CharField(max_length=255)
    column_name = models.CharField(max_length=255)
    display_label = models.CharField(max_length=255, blank=True)
    dimension_type = models.CharField(max_length=32, choices=DIMENSION_TYPE_CHOICES, default='categorical')
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ('semantic_model', 'name')

    def __str__(self):
        return f"{self.name} ({self.dimension_type})"

class SemanticMeasure(models.Model):
    AGGREGATION_CHOICES = [
        ('sum', 'Sum'),
        ('avg', 'Average'),
        ('count', 'Count (Rows)'),
        ('distinct_count', 'Distinct Count'),
        ('min', 'Minimum'),
        ('max', 'Maximum'),
        ('formula', 'Calculated Formula'),
    ]

    FORMAT_CHOICES = [
        ('currency', 'Currency (e.g. ₹ / $)'),
        ('percentage', 'Percentage (%)'),
        ('number', 'Standard Number'),
        ('integer', 'Integer'),
    ]

    semantic_model = models.ForeignKey(SemanticModel, on_delete=models.CASCADE, related_name='measures')
    name = models.CharField(max_length=255)
    display_label = models.CharField(max_length=255, blank=True)
    column_name = models.CharField(max_length=255, blank=True)
    aggregation_type = models.CharField(max_length=20, choices=AGGREGATION_CHOICES, default='sum')
    formula_expression = models.CharField(max_length=512, blank=True)
    format_type = models.CharField(max_length=20, choices=FORMAT_CHOICES, default='number')
    currency_symbol = models.CharField(max_length=10, default='₹', blank=True)
    decimal_places = models.PositiveSmallIntegerField(default=2)
    is_kpi = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ('semantic_model', 'name')

    def __str__(self):
        return f"{self.name} ({self.aggregation_type})"
