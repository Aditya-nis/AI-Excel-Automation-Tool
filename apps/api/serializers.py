from rest_framework import serializers
from django.contrib.auth import get_user_model
from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.datasets.models import SourceFile, Dataset, DatasetVersion, DatasetColumn, ColumnProfile
from apps.understanding.models import UnderstandingAssessment
from apps.data_quality.models import DataQualityIssue, DataQualityReport
from apps.cleaning.models import TransformationRun, TransformationStep, CleaningRecipe
from apps.consolidation.models import ConsolidationRun, ReconciliationRun
from apps.semantic_model.models import SemanticModel, SemanticDimension, SemanticMeasure
from apps.ask_data.models import ChatSession, QueryRun
from apps.reports.models import ReportDefinition, ReportRun
from apps.automation.models import WorkflowSchedule, JobRun
from apps.audit.models import AuditEvent
from apps.anomalies.models import AnomalyEvent, MetricForecast
from apps.notifications.models import Notification
from apps.approvals.models import ApprovalRequest

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class WorkspaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ['id', 'name', 'slug', 'description', 'owner', 'created_at', 'updated_at']
        read_only_fields = ['owner', 'created_at', 'updated_at']

class SourceFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceFile
        fields = ['id', 'filename', 'file_format', 'file_size_bytes', 'sha256_hash', 'sheet_names', 'selected_sheet', 'status', 'created_at']
        read_only_fields = ['file_size_bytes', 'sha256_hash', 'sheet_names', 'status', 'created_at']

class ColumnProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ColumnProfile
        fields = [
            'null_count', 'null_percentage', 'distinct_count', 'unique_percentage',
            'min_value', 'max_value', 'mean_value', 'std_value', 'median_value',
            'q25', 'q75', 'outlier_count', 'sample_values', 'top_categories'
        ]

class DatasetColumnSerializer(serializers.ModelSerializer):
    profile = ColumnProfileSerializer(read_only=True)

    class Meta:
        model = DatasetColumn
        fields = [
            'id', 'name', 'original_name', 'display_label', 'ordinal_position',
            'data_type', 'inferred_role', 'confidence_score', 'confidence_band',
            'evidence', 'is_primary_key', 'is_user_overridden', 'profile'
        ]

class DatasetVersionSerializer(serializers.ModelSerializer):
    columns = DatasetColumnSerializer(many=True, read_only=True)

    class Meta:
        model = DatasetVersion
        fields = [
            'id', 'version_number', 'parent_version', 'row_count', 'column_count',
            'quality_score', 'is_cleaned', 'change_summary', 'created_at', 'columns'
        ]

class DatasetSerializer(serializers.ModelSerializer):
    active_version_number = serializers.SerializerMethodField()
    row_count = serializers.SerializerMethodField()
    column_count = serializers.SerializerMethodField()
    quality_score = serializers.SerializerMethodField()

    class Meta:
        model = Dataset
        fields = [
            'id', 'name', 'description', 'active_version', 'active_version_number',
            'row_count', 'column_count', 'quality_score', 'created_at', 'updated_at'
        ]

    def get_active_version_number(self, obj):
        return obj.active_version.version_number if obj.active_version else None

    def get_row_count(self, obj):
        return obj.active_version.row_count if obj.active_version else 0

    def get_column_count(self, obj):
        return obj.active_version.column_count if obj.active_version else 0

    def get_quality_score(self, obj):
        return obj.active_version.quality_score if obj.active_version else 100.0

class UnderstandingAssessmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnderstandingAssessment
        fields = [
            'id', 'column_name', 'inferred_role', 'confidence_score',
            'confidence_band', 'evidence', 'sample_patterns', 'review_status',
            'user_override_role', 'reviewed_at', 'created_at'
        ]

class DataQualityIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataQualityIssue
        fields = [
            'id', 'column_name', 'issue_type', 'severity', 'affected_row_count',
            'evidence_summary', 'sample_row_indices', 'suggested_action',
            'suggested_params', 'is_resolved', 'created_at'
        ]

class DataQualityReportSerializer(serializers.ModelSerializer):
    issues = DataQualityIssueSerializer(source='version.quality_issues', many=True, read_only=True)

    class Meta:
        model = DataQualityReport
        fields = [
            'id', 'overall_score', 'completeness_score', 'uniqueness_score',
            'validity_score', 'consistency_score', 'scoring_formula',
            'total_issues_count', 'created_at', 'issues'
        ]

class TransformationStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransformationStep
        fields = ['id', 'step_number', 'operation_type', 'column_name', 'parameters', 'affected_rows', 'description']

class TransformationRunSerializer(serializers.ModelSerializer):
    steps = TransformationStepSerializer(many=True, read_only=True)

    class Meta:
        model = TransformationRun
        fields = [
            'id', 'run_type', 'status', 'steps_count', 'rows_before',
            'rows_after', 'error_message', 'created_at', 'steps'
        ]

class CleaningRecipeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CleaningRecipe
        fields = [
            'id', 'name', 'description', 'target_schema', 'steps_config',
            'version_number', 'is_active', 'created_at', 'updated_at'
        ]

class ConsolidationRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsolidationRun
        fields = [
            'id', 'operation_type', 'primary_dataset', 'secondary_dataset',
            'resulting_dataset', 'join_type', 'join_keys', 'cardinality_preview',
            'records_produced', 'status', 'created_at'
        ]

class ReconciliationRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationRun
        fields = [
            'id', 'name', 'primary_dataset', 'secondary_dataset', 'matching_keys',
            'matched_records_count', 'unmatched_primary_count', 'unmatched_secondary_count',
            'control_total_sum_1', 'control_total_sum_2', 'variance', 'tolerance',
            'is_reconciled', 'report_summary', 'created_at'
        ]

class SemanticDimensionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SemanticDimension
        fields = ['id', 'name', 'column_name', 'display_label', 'dimension_type', 'description']

class SemanticMeasureSerializer(serializers.ModelSerializer):
    class Meta:
        model = SemanticMeasure
        fields = [
            'id', 'name', 'display_label', 'column_name', 'aggregation_type',
            'formula_expression', 'format_type', 'currency_symbol', 'decimal_places',
            'is_kpi', 'description'
        ]

class SemanticModelSerializer(serializers.ModelSerializer):
    dimensions = SemanticDimensionSerializer(many=True, read_only=True)
    measures = SemanticMeasureSerializer(many=True, read_only=True)

    class Meta:
        model = SemanticModel
        fields = [
            'id', 'name', 'description', 'primary_dataset', 'is_default',
            'dimensions', 'measures', 'created_at', 'updated_at'
        ]

class QueryRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = QueryRun
        fields = [
            'id', 'user_query', 'parsed_intent', 'generated_query_plan',
            'result_data', 'caveats', 'confidence_score', 'execution_time_ms',
            'recommended_chart', 'error_message', 'created_at'
        ]

class ChatSessionSerializer(serializers.ModelSerializer):
    queries = QueryRunSerializer(many=True, read_only=True)

    class Meta:
        model = ChatSession
        fields = ['id', 'title', 'dataset', 'semantic_model', 'created_at', 'updated_at', 'queries']

class ReportDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportDefinition
        fields = [
            'id', 'name', 'report_type', 'description', 'dataset',
            'semantic_model', 'date_column', 'metric_columns', 'dimension_columns',
            'filters_config', 'version_number', 'created_at', 'updated_at'
        ]

class ReportRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportRun
        fields = [
            'id', 'report_definition', 'dataset_version', 'summary_kpis',
            'table_data', 'chart_payloads', 'excel_export_path',
            'pdf_export_path', 'csv_export_path', 'generated_at'
        ]

class WorkflowScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowSchedule
        fields = [
            'id', 'name', 'description', 'dataset', 'cleaning_recipe',
            'report_definition', 'cron_expression', 'timezone_name',
            'is_active', 'dry_run_mode', 'stop_on_drift', 'last_run_at',
            'next_run_at', 'created_at', 'updated_at'
        ]

class JobRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobRun
        fields = [
            'id', 'workflow', 'status', 'trigger_type', 'schema_drift_detected',
            'drift_details', 'execution_logs', 'output_version', 'started_at',
            'completed_at', 'duration_seconds'
        ]

class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            'id', 'timestamp', 'actor_username', 'event_type', 'object_type',
            'object_id', 'description', 'metadata', 'ip_address'
        ]

class AnomalyEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnomalyEvent
        fields = [
            'id', 'workspace', 'dataset', 'metric_name', 'observed_value',
            'baseline_value', 'deviation_percent', 'z_score', 'severity',
            'detection_method', 'evidence', 'period_label', 'review_status',
            'detected_at'
        ]

class MetricForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetricForecast
        fields = [
            'id', 'dataset', 'metric_name', 'date_column', 'method',
            'historical_points', 'horizon_periods', 'forecast_results',
            'mae_error', 'assumptions', 'created_at'
        ]

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'recipient', 'workspace', 'title', 'message',
            'level', 'link_url', 'is_read', 'created_at'
        ]

class ApprovalRequestSerializer(serializers.ModelSerializer):
    requester_name = serializers.ReadOnlyField(source='requester.username')
    reviewer_name = serializers.ReadOnlyField(source='reviewed_by.username')

    class Meta:
        model = ApprovalRequest
        fields = [
            'id', 'workspace', 'requester', 'requester_name', 'request_type',
            'target_object_type', 'target_object_id', 'title', 'description',
            'status', 'reviewed_by', 'reviewer_name', 'review_comments',
            'reviewed_at', 'created_at'
        ]

