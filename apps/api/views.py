import json
from rest_framework import viewsets, status, views, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
from django.http import FileResponse, Http404

from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.datasets.models import SourceFile, Dataset, DatasetVersion, DatasetColumn
from apps.datasets.services import save_source_file, ingest_file_to_dataset, load_version_dataframe
from apps.data_quality.models import DataQualityIssue, DataQualityReport
from apps.understanding.models import UnderstandingAssessment
from apps.cleaning.models import TransformationRun, CleaningRecipe
from apps.cleaning.services import preview_transformations, execute_transformations, undo_transformation, restore_version
from apps.consolidation.models import ConsolidationRun, ReconciliationRun
from apps.consolidation.services import preview_join_cardinality, execute_consolidation, execute_reconciliation
from apps.semantic_model.models import SemanticModel, SemanticDimension, SemanticMeasure
from apps.semantic_model.services import auto_generate_semantic_model
from apps.ask_data.models import ChatSession, QueryRun
from apps.ask_data.services import handle_user_query
from apps.reports.models import ReportDefinition, ReportRun
from apps.reports.services import generate_mis_report
from apps.automation.models import WorkflowSchedule, JobRun
from apps.automation.services import run_workflow_job
from apps.audit.models import AuditEvent
from apps.audit.services import log_audit
from apps.anomalies.models import AnomalyEvent, MetricForecast
from apps.anomalies.services import detect_anomalies_for_dataset, generate_metric_forecast
from apps.notifications.models import Notification
from apps.notifications.services import notify_user
from apps.approvals.models import ApprovalRequest
from apps.approvals.services import request_approval, decide_approval

from apps.api.serializers import (
    WorkspaceSerializer, SourceFileSerializer, DatasetSerializer, DatasetVersionSerializer,
    DatasetColumnSerializer, UnderstandingAssessmentSerializer, DataQualityReportSerializer,
    DataQualityIssueSerializer, TransformationRunSerializer, CleaningRecipeSerializer,
    ConsolidationRunSerializer, ReconciliationRunSerializer, SemanticModelSerializer,
    ChatSessionSerializer, QueryRunSerializer, ReportDefinitionSerializer, ReportRunSerializer,
    WorkflowScheduleSerializer, JobRunSerializer, AuditEventSerializer,
    AnomalyEventSerializer, MetricForecastSerializer, NotificationSerializer, ApprovalRequestSerializer
)

class WorkspaceViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceSerializer

    def get_queryset(self):
        return Workspace.objects.filter(memberships__user=self.request.user)

    def perform_create(self, serializer):
        workspace = serializer.save(owner=self.request.user)
        WorkspaceMembership.objects.create(
            workspace=workspace,
            user=self.request.user,
            role='admin',
            is_default=False
        )

    @action(detail=True, methods=['post'])
    def switch(self, request, pk=None):
        workspace = self.get_object()
        request.session['active_workspace_id'] = workspace.id
        return Response({'status': 'active workspace switched', 'workspace_id': workspace.id, 'name': workspace.name})

class FileViewSet(viewsets.ModelViewSet):
    serializer_class = SourceFileSerializer

    def get_queryset(self):
        workspace = getattr(self.request, 'workspace', None)
        if not workspace:
            return SourceFile.objects.none()
        return SourceFile.objects.filter(workspace=workspace)

    def create(self, request, *args, **kwargs):
        workspace = getattr(request, 'workspace', None)
        if not workspace:
            return Response({'error': 'No active workspace selected'}, status=status.HTTP_400_BAD_REQUEST)
        
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file uploaded'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            source_file = save_source_file(file_obj, workspace, request.user)
            
            # If auto-ingest is requested or sheet is ready
            auto_ingest = request.data.get('auto_ingest', 'true').lower() in ('true', '1')
            sheet_name = request.data.get('sheet_name', '')
            dataset = None
            if auto_ingest:
                dataset, version = ingest_file_to_dataset(
                    source_file=source_file,
                    sheet_name=sheet_name or None,
                    user=request.user
                )

            data = SourceFileSerializer(source_file).data
            if dataset:
                data['dataset_id'] = dataset.id
                data['dataset_name'] = dataset.name
                data['active_version'] = dataset.active_version.version_number
            return Response(data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class DatasetViewSet(viewsets.ModelViewSet):
    serializer_class = DatasetSerializer

    def get_queryset(self):
        workspace = getattr(self.request, 'workspace', None)
        if not workspace:
            return Dataset.objects.none()
        return Dataset.objects.filter(workspace=workspace)

    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        dataset = self.get_object()
        version = dataset.active_version
        if not version:
            return Response({'error': 'Dataset has no active version'}, status=status.HTTP_404_NOT_FOUND)

        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 50)), 200)
        sort_by = request.query_params.get('sort_by')
        sort_desc = request.query_params.get('sort_desc', 'false').lower() == 'true'
        search = request.query_params.get('q', '').strip().lower()

        df = load_version_dataframe(version)
        
        if search:
            mask = df.astype(str).apply(lambda row: row.str.lower().str.contains(search, regex=False).any(), axis=1)
            df = df[mask]

        if sort_by and sort_by in df.columns:
            df = df.sort_values(by=sort_by, ascending=not sort_desc)

        total_records = len(df)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_df = df.iloc[start_idx:end_idx]

        columns_meta = DatasetColumnSerializer(version.columns.all(), many=True).data

        # Convert records safely
        records = page_df.replace({float('nan'): None}).to_dict(orient='records')

        return Response({
            'dataset_id': dataset.id,
            'dataset_name': dataset.name,
            'version_number': version.version_number,
            'quality_score': version.quality_score,
            'total_rows': total_records,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_records + page_size - 1) // page_size if total_records > 0 else 1,
            'columns': columns_meta,
            'records': records,
        })

    @action(detail=True, methods=['get'])
    def versions(self, request, pk=None):
        dataset = self.get_object()
        versions = dataset.versions.all().order_by('-version_number')
        return Response(DatasetVersionSerializer(versions, many=True).data)

    @action(detail=True, methods=['post'])
    def undo(self, request, pk=None):
        dataset = self.get_object()
        try:
            parent = undo_transformation(dataset, request.user)
            return Response({
                'status': 'undone',
                'active_version': parent.version_number,
                'rows': parent.row_count,
                'columns': parent.column_count
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        dataset = self.get_object()
        version_num = request.data.get('version_number')
        if not version_num:
            return Response({'error': 'version_number required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            target = restore_version(dataset, int(version_num), request.user)
            return Response({
                'status': 'restored',
                'active_version': target.version_number
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class QualityViewSet(viewsets.ViewSet):
    def list(self, request):
        dataset_id = request.query_params.get('dataset_id')
        if not dataset_id:
            return Response({'error': 'dataset_id required'}, status=status.HTTP_400_BAD_REQUEST)
        dataset = get_object_or_404(Dataset, id=dataset_id, workspace=request.workspace)
        version = dataset.active_version
        report = getattr(version, 'quality_report', None)
        if not report:
            from apps.data_quality.services import evaluate_data_quality
            df = load_version_dataframe(version)
            report = evaluate_data_quality(version, df)
        return Response(DataQualityReportSerializer(report).data)

    @action(detail=False, methods=['post'])
    def quick_fix(self, request):
        issue_id = request.data.get('issue_id')
        issue = get_object_or_404(DataQualityIssue, id=issue_id)
        dataset = issue.version.dataset
        step = {
            'operation_type': issue.suggested_action,
            'column_name': issue.column_name,
            'parameters': issue.suggested_params,
        }
        new_version = execute_transformations(dataset, [step], user=request.user)
        issue.is_resolved = True
        issue.save()
        return Response({
            'status': 'fixed',
            'new_version': new_version.version_number,
            'quality_score': new_version.quality_score
        })

class UnderstandingViewSet(viewsets.ViewSet):
    def list(self, request):
        dataset_id = request.query_params.get('dataset_id')
        if not dataset_id:
            return Response({'error': 'dataset_id required'}, status=status.HTTP_400_BAD_REQUEST)
        dataset = get_object_or_404(Dataset, id=dataset_id, workspace=request.workspace)
        version = dataset.active_version
        assessments = UnderstandingAssessment.objects.filter(version=version)
        return Response(UnderstandingAssessmentSerializer(assessments, many=True).data)

    @action(detail=False, methods=['post'])
    def review(self, request):
        assessment_id = request.data.get('assessment_id')
        action_type = request.data.get('action') # accept, override
        new_role = request.data.get('override_role', '')

        assessment = get_object_or_404(UnderstandingAssessment, id=assessment_id)
        if action_type == 'accept':
            assessment.review_status = 'accepted'
        elif action_type == 'override':
            assessment.review_status = 'overridden'
            assessment.user_override_role = new_role
            # Update column
            col = DatasetColumn.objects.filter(version=assessment.version, name=assessment.column_name).first()
            if col:
                col.inferred_role = new_role
                col.is_user_overridden = True
                col.save()
        assessment.reviewed_by = request.user
        assessment.save()
        return Response(UnderstandingAssessmentSerializer(assessment).data)

class CleaningViewSet(viewsets.ViewSet):
    @action(detail=False, methods=['post'])
    def preview(self, request):
        dataset_id = request.data.get('dataset_id')
        steps = request.data.get('steps', [])
        dataset = get_object_or_404(Dataset, id=dataset_id, workspace=request.workspace)
        preview_data = preview_transformations(dataset, steps)
        return Response(preview_data)

    @action(detail=False, methods=['post'])
    def execute(self, request):
        dataset_id = request.data.get('dataset_id')
        steps = request.data.get('steps', [])
        dataset = get_object_or_404(Dataset, id=dataset_id, workspace=request.workspace)
        new_version = execute_transformations(dataset, steps, user=request.user)
        return Response({
            'status': 'transformed',
            'version_number': new_version.version_number,
            'rows': new_version.row_count,
            'columns': new_version.column_count,
            'quality_score': new_version.quality_score
        })

    @action(detail=False, methods=['get'])
    def recipes(self, request):
        recipes = CleaningRecipe.objects.filter(workspace=request.workspace)
        return Response(CleaningRecipeSerializer(recipes, many=True).data)

    @action(detail=False, methods=['post'])
    def save_recipe(self, request):
        name = request.data.get('name')
        dataset_id = request.data.get('dataset_id')
        steps = request.data.get('steps', [])
        dataset = get_object_or_404(Dataset, id=dataset_id, workspace=request.workspace)
        target_schema = {'columns': list(dataset.active_version.columns.values_list('name', flat=True))}
        recipe = CleaningRecipe.objects.create(
            workspace=request.workspace,
            name=name,
            description=request.data.get('description', ''),
            target_schema=target_schema,
            steps_config=steps,
            created_by=request.user
        )
        return Response(CleaningRecipeSerializer(recipe).data, status=status.HTTP_201_CREATED)

class ConsolidationViewSet(viewsets.ViewSet):
    @action(detail=False, methods=['post'])
    def preview_cardinality(self, request):
        p_id = request.data.get('primary_dataset_id')
        s_id = request.data.get('secondary_dataset_id')
        pk = request.data.get('primary_key')
        sk = request.data.get('secondary_key')

        d1 = get_object_or_404(Dataset, id=p_id, workspace=request.workspace)
        d2 = get_object_or_404(Dataset, id=s_id, workspace=request.workspace)
        df1 = load_version_dataframe(d1.active_version)
        df2 = load_version_dataframe(d2.active_version)

        card = preview_join_cardinality(df1, df2, pk, sk)
        return Response(card)

    @action(detail=False, methods=['post'])
    def execute(self, request):
        op_type = request.data.get('operation_type') # append or join
        p_id = request.data.get('primary_dataset_id')
        s_id = request.data.get('secondary_dataset_id')
        params = request.data.get('params', {})

        d1 = get_object_or_404(Dataset, id=p_id, workspace=request.workspace)
        d2 = get_object_or_404(Dataset, id=s_id, workspace=request.workspace)

        new_dataset = execute_consolidation(request.workspace, op_type, d1, d2, params, user=request.user)
        return Response(DatasetSerializer(new_dataset).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def reconcile(self, request):
        p_id = request.data.get('primary_dataset_id')
        s_id = request.data.get('secondary_dataset_id')
        pk = request.data.get('primary_key')
        sk = request.data.get('secondary_key')
        m1 = request.data.get('control_total_field_1')
        m2 = request.data.get('control_total_field_2')
        tol = float(request.data.get('tolerance', 0.0))

        d1 = get_object_or_404(Dataset, id=p_id, workspace=request.workspace)
        d2 = get_object_or_404(Dataset, id=s_id, workspace=request.workspace)

        run = execute_reconciliation(request.workspace, d1, d2, pk, sk, m1, m2, tol, user=request.user)
        return Response(ReconciliationRunSerializer(run).data)

class SemanticModelViewSet(viewsets.ModelViewSet):
    serializer_class = SemanticModelSerializer

    def get_queryset(self):
        return SemanticModel.objects.filter(workspace=self.request.workspace)

    @action(detail=False, methods=['post'])
    def auto_generate(self, request):
        dataset_id = request.data.get('dataset_id')
        dataset = get_object_or_404(Dataset, id=dataset_id, workspace=request.workspace)
        model = auto_generate_semantic_model(dataset, request.user)
        return Response(SemanticModelSerializer(model).data)

class AskDataViewSet(viewsets.ViewSet):
    @action(detail=False, methods=['post'])
    def query(self, request):
        dataset_id = request.data.get('dataset_id')
        query_text = request.data.get('query', '').strip()
        session_id = request.data.get('session_id')

        if not dataset_id or not query_text:
            return Response({'error': 'dataset_id and query required'}, status=status.HTTP_400_BAD_REQUEST)

        dataset = get_object_or_404(Dataset, id=dataset_id, workspace=request.workspace)
        
        session = None
        if session_id:
            session = ChatSession.objects.filter(id=session_id, workspace=request.workspace).first()
        if not session:
            session = ChatSession.objects.create(
                workspace=request.workspace,
                dataset=dataset,
                title=f"Analytics: {query_text[:30]}",
                user=request.user
            )

        query_run = handle_user_query(session, query_text, user=request.user)
        return Response({
            'session_id': session.id,
            'query_run': QueryRunSerializer(query_run).data
        })

class ReportViewSet(viewsets.ModelViewSet):
    serializer_class = ReportDefinitionSerializer

    def get_queryset(self):
        return ReportDefinition.objects.filter(workspace=self.request.workspace)

    @action(detail=True, methods=['post'])
    def generate(self, request, pk=None):
        report_def = self.get_object()
        params = request.data.get('parameters', {})
        run = generate_mis_report(report_def, user=request.user, parameters=params)
        return Response(ReportRunSerializer(run).data)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        report_def = self.get_object()
        run_id = request.query_params.get('run_id')
        fmt = request.query_params.get('format', 'excel') # excel, pdf, csv
        
        run = ReportRun.objects.filter(report_definition=report_def)
        if run_id:
            run = run.filter(id=run_id)
        run = run.first()

        if not run:
            raise Http404("No report run found")

        path = run.excel_export_path if fmt == 'excel' else (run.pdf_export_path if fmt == 'pdf' else run.csv_export_path)
        if not path or not os.path.exists(path):
            raise Http404(f"Export file for {fmt} not found")

        content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if fmt == 'excel' else ('application/pdf' if fmt == 'pdf' else 'text/csv')
        return FileResponse(open(path, 'rb'), content_type=content_type, as_attachment=True, filename=os.path.basename(path))

class AutomationViewSet(viewsets.ModelViewSet):
    serializer_class = WorkflowScheduleSerializer

    def get_queryset(self):
        return WorkflowSchedule.objects.filter(workspace=self.request.workspace)

    @action(detail=True, methods=['post'])
    def run_now(self, request, pk=None):
        workflow = self.get_object()
        job = run_workflow_job(workflow, trigger_type='manual', user=request.user)
        return Response(JobRunSerializer(job).data)

class JobViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = JobRunSerializer

    def get_queryset(self):
        return JobRun.objects.filter(workflow__workspace=self.request.workspace)

class AuditViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        qs = AuditEvent.objects.all()
        workspace = getattr(self.request, 'workspace', None)
        if workspace:
            qs = qs.filter(workspace=workspace)
        return qs[:200]

class AnomalyViewSet(viewsets.ModelViewSet):
    serializer_class = AnomalyEventSerializer

    def get_queryset(self):
        return AnomalyEvent.objects.filter(workspace=self.request.workspace)

    @action(detail=False, methods=['post'])
    def scan(self, request):
        dataset_id = request.data.get('dataset_id')
        if not dataset_id:
            return Response({'error': 'dataset_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        dataset = get_object_or_404(Dataset, id=dataset_id, workspace=request.workspace)
        anomalies = detect_anomalies_for_dataset(dataset, user=request.user)
        return Response({
            'status': 'scan completed',
            'count': len(anomalies),
            'anomalies': AnomalyEventSerializer(anomalies, many=True).data
        })

    @action(detail=False, methods=['post'])
    def forecast(self, request):
        dataset_id = request.data.get('dataset_id')
        metric_name = request.data.get('metric_name')
        date_column = request.data.get('date_column')
        horizon = int(request.data.get('horizon', 3))
        if not dataset_id or not metric_name or not date_column:
            return Response({'error': 'dataset_id, metric_name, and date_column are required'}, status=status.HTTP_400_BAD_REQUEST)
        dataset = get_object_or_404(Dataset, id=dataset_id, workspace=request.workspace)
        try:
            fc = generate_metric_forecast(dataset, metric_name, date_column, horizon=horizon, user=request.user)
            return Response(MetricForecastSerializer(fc).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        anomaly = self.get_object()
        new_status = request.data.get('status', 'acknowledged')
        anomaly.review_status = new_status
        anomaly.save()
        return Response({'status': 'updated', 'review_status': anomaly.review_status})

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notif = self.get_object()
        notif.is_read = True
        notif.save()
        return Response({'status': 'marked read'})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'status': 'all marked read'})

class ApprovalViewSet(viewsets.ModelViewSet):
    serializer_class = ApprovalRequestSerializer

    def get_queryset(self):
        return ApprovalRequest.objects.filter(workspace=self.request.workspace)

    @action(detail=False, methods=['post'])
    def create_request(self, request):
        title = request.data.get('title')
        request_type = request.data.get('request_type', 'report_publication')
        description = request.data.get('description', '')
        target_type = request.data.get('target_type', '')
        target_id = request.data.get('target_id', '')
        if not title:
            return Response({'error': 'title is required'}, status=status.HTTP_400_BAD_REQUEST)
        req = request_approval(
            workspace=request.workspace,
            requester=request.user,
            request_type=request_type,
            title=title,
            description=description,
            target_type=target_type,
            target_id=target_id
        )
        return Response(ApprovalRequestSerializer(req).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def decide(self, request, pk=None):
        req_obj = self.get_object()
        action_decision = request.data.get('action') # 'approved' or 'rejected'
        comments = request.data.get('comments', '')
        if action_decision not in ['approved', 'rejected']:
            return Response({'error': 'action must be approved or rejected'}, status=status.HTTP_400_BAD_REQUEST)
        decided = decide_approval(req_obj, reviewer=request.user, action=action_decision, comments=comments)
        return Response(ApprovalRequestSerializer(decided).data)

