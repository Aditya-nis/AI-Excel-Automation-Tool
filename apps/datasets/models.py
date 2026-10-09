import os
import hashlib
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()

class SourceFile(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]

    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='source_files')
    file = models.FileField(upload_to='source_files/%Y/%m/')
    filename = models.CharField(max_length=255)
    file_format = models.CharField(max_length=10)
    file_size_bytes = models.BigIntegerField(default=0)
    sha256_hash = models.CharField(max_length=64, db_index=True)
    sheet_names = models.JSONField(default=list, blank=True)
    selected_sheet = models.CharField(max_length=128, blank=True)
    encoding = models.CharField(max_length=32, default='utf-8')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.filename} ({self.workspace.name})"

    @staticmethod
    def calculate_sha256(file_obj):
        hasher = hashlib.sha256()
        for chunk in file_obj.chunks():
            hasher.update(chunk)
        file_obj.seek(0)
        return hasher.hexdigest()

class Dataset(models.Model):
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='datasets')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    source_file = models.ForeignKey(SourceFile, on_delete=models.SET_NULL, null=True, blank=True, related_name='datasets')
    active_version = models.ForeignKey('DatasetVersion', on_delete=models.SET_NULL, null=True, blank=True, related_name='active_for_datasets')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = ('workspace', 'name')

    def __str__(self):
        return f"{self.name} ({self.workspace.name})"

class DatasetVersion(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField()
    parent_version = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='child_versions')
    transformation_run = models.ForeignKey('cleaning.TransformationRun', on_delete=models.SET_NULL, null=True, blank=True, related_name='output_versions')
    file_path = models.CharField(max_length=512)
    row_count = models.PositiveIntegerField(default=0)
    column_count = models.PositiveIntegerField(default=0)
    quality_score = models.FloatField(default=100.0)
    is_cleaned = models.BooleanField(default=False)
    change_summary = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version_number']
        unique_together = ('dataset', 'version_number')

    def __str__(self):
        return f"{self.dataset.name} v{self.version_number}"

class DatasetColumn(models.Model):
    DATA_TYPE_CHOICES = [
        ('text', 'Text'),
        ('integer', 'Integer'),
        ('decimal', 'Decimal / Float'),
        ('date', 'Date'),
        ('datetime', 'DateTime'),
        ('boolean', 'Boolean'),
        ('category', 'Category'),
        ('id', 'Identifier'),
    ]

    ROLE_CHOICES = [
        ('measure', 'Measure (Numeric Amount)'),
        ('dimension', 'Dimension (Categorical)'),
        ('date', 'Date / Time Period'),
        ('identifier', 'Unique Identifier / Key'),
        ('currency', 'Monetary Currency'),
        ('percentage', 'Percentage / Rate'),
        ('quantity', 'Quantity / Count'),
        ('status', 'Status / Lifecycle'),
        ('text', 'General Text'),
        ('unknown', 'Unknown'),
    ]

    BAND_CHOICES = [
        ('high', 'High (>=0.90)'),
        ('medium', 'Medium (0.70 - 0.89)'),
        ('low', 'Low (<0.70)'),
    ]

    version = models.ForeignKey(DatasetVersion, on_delete=models.CASCADE, related_name='columns')
    name = models.CharField(max_length=255)
    original_name = models.CharField(max_length=255)
    display_label = models.CharField(max_length=255, blank=True)
    ordinal_position = models.PositiveIntegerField()
    data_type = models.CharField(max_length=20, choices=DATA_TYPE_CHOICES, default='text')
    inferred_role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='unknown')
    confidence_score = models.FloatField(default=0.0)
    confidence_band = models.CharField(max_length=10, choices=BAND_CHOICES, default='low')
    evidence = models.TextField(blank=True)
    is_primary_key = models.BooleanField(default=False)
    is_user_overridden = models.BooleanField(default=False)

    class Meta:
        ordering = ['ordinal_position']
        unique_together = ('version', 'name')

    def __str__(self):
        return f"{self.name} ({self.data_type}, role: {self.inferred_role})"

class ColumnProfile(models.Model):
    column = models.OneToOneField(DatasetColumn, on_delete=models.CASCADE, related_name='profile')
    null_count = models.PositiveIntegerField(default=0)
    null_percentage = models.FloatField(default=0.0)
    distinct_count = models.PositiveIntegerField(default=0)
    unique_percentage = models.FloatField(default=0.0)
    min_value = models.CharField(max_length=255, null=True, blank=True)
    max_value = models.CharField(max_length=255, null=True, blank=True)
    mean_value = models.FloatField(null=True, blank=True)
    std_value = models.FloatField(null=True, blank=True)
    median_value = models.FloatField(null=True, blank=True)
    q25 = models.FloatField(null=True, blank=True)
    q75 = models.FloatField(null=True, blank=True)
    outlier_count = models.PositiveIntegerField(default=0)
    sample_values = models.JSONField(default=list, blank=True)
    top_categories = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"Profile for {self.column.name}"
