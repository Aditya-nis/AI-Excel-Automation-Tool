import json
import re
import pandas as pd
import numpy as np
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Avg, Sum, Count

from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.datasets.models import SourceFile, Dataset, DatasetVersion, DatasetColumn
from apps.datasets.services import load_version_dataframe
from apps.data_quality.models import DataQualityIssue, DataQualityReport
from apps.understanding.models import UnderstandingAssessment
from apps.cleaning.models import TransformationRun, CleaningRecipe
from apps.consolidation.models import ConsolidationRun, ReconciliationRun
from apps.semantic_model.models import SemanticModel
from apps.ask_data.models import ChatSession
from apps.reports.models import ReportDefinition, ReportRun
from apps.automation.models import WorkflowSchedule, JobRun
from apps.audit.models import AuditEvent
from apps.anomalies.models import AnomalyEvent, MetricForecast
from apps.anomalies.services import detect_anomalies_for_dataset
from apps.notifications.models import Notification
from apps.approvals.models import ApprovalRequest

def clean_numeric_series(series):
    """Safely converts string/object series to numeric, properly preserving accounting negatives e.g. (100.50)."""
    def _clean_val(val):
        if pd.isna(val):
            return float('nan')
        s = str(val).strip()
        if not s or s in ('nan', 'None', '<NA>'):
            return float('nan')
        is_neg = False
        if s.startswith('(') and s.endswith(')'):
            is_neg = True
            s = s[1:-1]
        elif s.startswith('-'):
            is_neg = True
            s = s[1:]
        elif s.endswith('-'):
            is_neg = True
            s = s[:-1]
        cleaned = re.sub(r'[\$,₹€£\s,]', '', s)
        try:
            num = float(cleaned)
            return -num if is_neg else num
        except (ValueError, TypeError):
            return float('nan')
    return series.apply(_clean_val)


@login_required
def dashboard_home(request):
    workspace = request.workspace
    datasets = Dataset.objects.filter(workspace=workspace)
    total_datasets = datasets.count()
    
    # Calculate stats
    total_rows = sum([d.active_version.row_count for d in datasets if d.active_version])
    avg_quality = round(DatasetVersion.objects.filter(dataset__in=datasets).aggregate(Avg('quality_score'))['quality_score__avg'] or 100.0, 1)
    total_reports = ReportRun.objects.filter(report_definition__workspace=workspace).count()

    selected_dataset_id = request.GET.get('dataset_id')
    selected_dataset = None
    if selected_dataset_id:
        selected_dataset = datasets.filter(id=selected_dataset_id).first()
    if not selected_dataset and datasets.exists():
        selected_dataset = datasets.first()

    preview_rows = []
    columns = []
    kpis = []
    chart_data = None

    if selected_dataset and selected_dataset.active_version:
        v = selected_dataset.active_version
        columns = v.columns.all()
        try:
            df = load_version_dataframe(v)
            preview_rows = df.head(15).replace({float('nan'): None}).to_dict(orient='records')
            
            # Compute KPI cards from currency / measure columns
            meas_cols = [c.name for c in columns if c.inferred_role in ['currency', 'measure', 'quantity'] or c.data_type in ['integer', 'decimal']][:4]
            for mc in meas_cols:
                s = clean_numeric_series(df[mc]).dropna()
                if len(s) > 0:
                    kpis.append({
                        'label': f"Total {mc.replace('_', ' ').title()}",
                        'value': f"{round(float(s.sum()), 2):,}",
                        'avg': f"{round(float(s.mean()), 2):,}",
                        'role': 'currency' if 'amount' in mc.lower() or 'sales' in mc.lower() or 'price' in mc.lower() else 'number'
                    })

            # Create default distribution chart from first category column
            cat_cols = [c.name for c in columns if c.inferred_role in ['dimension', 'status', 'category'] or c.data_type == 'category']
            if cat_cols and meas_cols:
                cdim = cat_cols[0]
                cmeas = meas_cols[0]
                df_c = df.copy()
                df_c['__m'] = clean_numeric_series(df_c[cmeas])
                grp = df_c.groupby(cdim)['__m'].sum().sort_values(ascending=False).head(8)
                chart_data = {
                    'labels': [str(k) for k in grp.index],
                    'values': [round(float(v), 2) for v in grp.values],
                    'title': f"{cmeas.replace('_', ' ').title()} by {cdim.replace('_', ' ').title()}"
                }
        except Exception as e:
            preview_rows = []

    recent_audits = AuditEvent.objects.filter(workspace=workspace)[:8]

    context = {
        'datasets': datasets,
        'selected_dataset': selected_dataset,
        'total_datasets': total_datasets,
        'total_rows': total_rows,
        'avg_quality': avg_quality,
        'total_reports': total_reports,
        'preview_rows': preview_rows,
        'columns': columns,
        'kpis': kpis,
        'chart_data': chart_data,
        'recent_audits': recent_audits,
    }
    return render(request, 'dashboards/home.html', context)

@login_required
def upload_view(request):
    workspace = request.workspace
    files = SourceFile.objects.filter(workspace=workspace)
    return render(request, 'datasets/upload.html', {'files': files})

@login_required
def dataset_detail_view(request, dataset_id):
    dataset = get_object_or_404(Dataset, id=dataset_id, workspace=request.workspace)
    version = dataset.active_version
    columns = version.columns.all() if version else []
    
    # Load sample preview
    preview_rows = []
    if version:
        try:
            df = load_version_dataframe(version)
            preview_rows = df.head(30).replace({float('nan'): None}).to_dict(orient='records')
        except Exception:
            pass

    return render(request, 'datasets/detail.html', {
        'dataset': dataset,
        'version': version,
        'columns': columns,
        'preview_rows': preview_rows,
    })

@login_required
def understanding_view(request, dataset_id):
    dataset = get_object_or_404(Dataset, id=dataset_id, workspace=request.workspace)
    version = dataset.active_version
    assessments = UnderstandingAssessment.objects.filter(version=version) if version else []
    return render(request, 'datasets/understanding.html', {
        'dataset': dataset,
        'version': version,
        'assessments': assessments,
    })

@login_required
def data_quality_view(request, dataset_id=None):
    workspace = request.workspace
    if dataset_id:
        dataset = get_object_or_404(Dataset, id=dataset_id, workspace=workspace)
    else:
        dataset = Dataset.objects.filter(workspace=workspace).first()
    version = dataset.active_version if dataset else None
    report = getattr(version, 'quality_report', None) if version else None
    issues = version.quality_issues.all() if version else []
    return render(request, 'quality/center.html', {
        'dataset': dataset,
        'version': version,
        'report': report,
        'issues': issues,
    })

@login_required
def transformations_view(request, dataset_id):
    dataset = get_object_or_404(Dataset, id=dataset_id, workspace=request.workspace)
    versions = dataset.versions.all().order_by('-version_number')
    runs = dataset.transformation_runs.all()
    recipes = CleaningRecipe.objects.filter(workspace=request.workspace)
    return render(request, 'cleaning/history.html', {
        'dataset': dataset,
        'versions': versions,
        'runs': runs,
        'recipes': recipes,
    })

@login_required
def consolidation_view(request):
    workspace = request.workspace
    datasets = Dataset.objects.filter(workspace=workspace)
    runs = ConsolidationRun.objects.filter(workspace=workspace)
    reconciliations = ReconciliationRun.objects.filter(workspace=workspace)
    return render(request, 'consolidation/index.html', {
        'datasets': datasets,
        'runs': runs,
        'reconciliations': reconciliations,
    })

@login_required
def semantic_models_view(request):
    workspace = request.workspace
    datasets = Dataset.objects.filter(workspace=workspace)
    models = SemanticModel.objects.filter(workspace=workspace)
    return render(request, 'dashboards/semantic_models.html', {
        'datasets': datasets,
        'models': models,
    })

@login_required
def ask_data_view(request):
    workspace = request.workspace
    datasets = Dataset.objects.filter(workspace=workspace)
    sessions = ChatSession.objects.filter(workspace=workspace)
    active_dataset = datasets.first() if datasets.exists() else None
    return render(request, 'ask_data/chat.html', {
        'datasets': datasets,
        'sessions': sessions,
        'active_dataset': active_dataset,
    })

@login_required
def reports_view(request):
    workspace = request.workspace
    datasets = Dataset.objects.filter(workspace=workspace)
    report_defs = ReportDefinition.objects.filter(workspace=workspace)
    report_runs = ReportRun.objects.filter(report_definition__workspace=workspace)
    return render(request, 'reports/builder.html', {
        'datasets': datasets,
        'report_defs': report_defs,
        'report_runs': report_runs,
    })

@login_required
def automation_view(request):
    workspace = request.workspace
    workflows = WorkflowSchedule.objects.filter(workspace=workspace)
    datasets = Dataset.objects.filter(workspace=workspace)
    recipes = CleaningRecipe.objects.filter(workspace=workspace)
    reports = ReportDefinition.objects.filter(workspace=workspace)
    return render(request, 'automation/workflows.html', {
        'workflows': workflows,
        'datasets': datasets,
        'recipes': recipes,
        'reports': reports,
    })

@login_required
def jobs_view(request):
    workspace = request.workspace
    jobs = JobRun.objects.filter(workflow__workspace=workspace)
    return render(request, 'automation/jobs.html', {'jobs': jobs})

@login_required
def audit_view(request):
    workspace = request.workspace
    events = AuditEvent.objects.filter(workspace=workspace)[:200]
    return render(request, 'audit/log.html', {'events': events})

@login_required
def settings_view(request):
    workspace = request.workspace
    memberships = WorkspaceMembership.objects.filter(workspace=workspace)
    return render(request, 'dashboards/settings.html', {
        'workspace': workspace,
        'memberships': memberships,
    })

@login_required
def visual_workflow_builder(request):
    workspace = request.workspace
    datasets = Dataset.objects.filter(workspace=workspace)
    recipes = CleaningRecipe.objects.filter(workspace=workspace)
    reports = ReportDefinition.objects.filter(workspace=workspace)
    return render(request, 'automation/builder.html', {
        'datasets': datasets,
        'recipes': recipes,
        'reports': reports,
    })

@login_required
def anomalies_view(request):
    workspace = request.workspace
    datasets = Dataset.objects.filter(workspace=workspace)
    anomalies = AnomalyEvent.objects.filter(workspace=workspace)
    forecasts = MetricForecast.objects.filter(dataset__workspace=workspace)
    return render(request, 'dashboards/anomalies.html', {
        'datasets': datasets,
        'anomalies': anomalies,
        'forecasts': forecasts,
    })

@login_required
def notifications_view(request):
    notifications = Notification.objects.filter(recipient=request.user)
    return render(request, 'notifications/index.html', {
        'notifications': notifications,
    })

@login_required
def approvals_view(request):
    workspace = request.workspace
    pending_approvals = ApprovalRequest.objects.filter(workspace=workspace, status='pending')
    history_approvals = ApprovalRequest.objects.filter(workspace=workspace).exclude(status='pending')
    return render(request, 'approvals/index.html', {
        'pending_approvals': pending_approvals,
        'history_approvals': history_approvals,
    })

# ==========================================
# ADVANCED MIS REPORT & ANALYTICS VIEWS
# ==========================================

@login_required
def mis_home_view(request):
    """Central Executive MIS Command Center."""
    workspace = request.workspace
    datasets = Dataset.objects.filter(workspace=workspace)
    total_datasets = datasets.count()
    total_rows = sum([d.active_version.row_count for d in datasets if d.active_version])
    avg_quality = round(DatasetVersion.objects.filter(dataset__in=datasets).aggregate(Avg('quality_score'))['quality_score__avg'] or 100.0, 1)
    
    report_runs = ReportRun.objects.filter(report_definition__workspace=workspace).order_by('-generated_at')
    total_reports = report_runs.count()
    recent_reports = report_runs[:6]

    # Open Exceptions count
    quality_issues_count = DataQualityIssue.objects.filter(version__dataset__workspace=workspace, is_resolved=False).count()
    anomalies_count = AnomalyEvent.objects.filter(workspace=workspace, review_status='open').count()
    total_exceptions = quality_issues_count + anomalies_count

    # Recent activity audit
    recent_audits = AuditEvent.objects.filter(workspace=workspace)[:6]

    # Quick metric summary from active dataset
    selected_dataset = datasets.first()
    kpi_summary = []
    if selected_dataset and selected_dataset.active_version:
        try:
            df = load_version_dataframe(selected_dataset.active_version)
            meas_cols = [c.name for c in selected_dataset.active_version.columns.all() if c.inferred_role in ['currency', 'measure', 'quantity'] or c.data_type in ['integer', 'decimal']][:4]
            for mc in meas_cols:
                num = pd.to_numeric(df[mc].astype(str).str.replace(r'[\$,₹€£\s,()]', '', regex=True), errors='coerce').dropna()
                if len(num) > 0:
                    kpi_summary.append({
                        'title': mc.replace('_', ' ').title(),
                        'total': f"{round(float(num.sum()), 2):,}",
                        'avg': f"{round(float(num.mean()), 2):,}",
                        'count': len(num)
                    })
        except Exception:
            pass

    return render(request, 'dashboards/mis_home.html', {
        'total_datasets': total_datasets,
        'total_rows': total_rows,
        'avg_quality': avg_quality,
        'total_reports': total_reports,
        'recent_reports': recent_reports,
        'total_exceptions': total_exceptions,
        'quality_issues_count': quality_issues_count,
        'anomalies_count': anomalies_count,
        'recent_audits': recent_audits,
        'kpi_summary': kpi_summary,
        'selected_dataset': selected_dataset,
    })

@login_required
def exception_center_view(request):
    """Exception Center aggregating data quality violations, outlier anomalies, and variances."""
    workspace = request.workspace
    quality_issues = DataQualityIssue.objects.filter(version__dataset__workspace=workspace)
    anomalies = AnomalyEvent.objects.filter(workspace=workspace)
    reconciliations = ReconciliationRun.objects.filter(workspace=workspace, is_reconciled=False)

    # Handle status resolution update
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')
        if action_type == 'resolve_quality' and item_id:
            DataQualityIssue.objects.filter(id=item_id, version__dataset__workspace=workspace).update(is_resolved=True)
            messages.success(request, f"Quality issue #{item_id} marked as resolved.")
        elif action_type == 'update_anomaly' and item_id:
            new_status = request.POST.get('new_status', 'resolved')
            AnomalyEvent.objects.filter(id=item_id, workspace=workspace).update(review_status=new_status)
            messages.success(request, f"Anomaly #{item_id} updated to {new_status}.")
        return redirect('exception_center')

    critical_count = anomalies.filter(severity='critical', review_status='open').count() + quality_issues.filter(severity='critical', is_resolved=False).count()
    warning_count = anomalies.filter(severity='warning', review_status='open').count() + quality_issues.filter(severity='warning', is_resolved=False).count()
    resolved_count = anomalies.filter(review_status='resolved').count() + quality_issues.filter(is_resolved=True).count()

    return render(request, 'dashboards/exception_center.html', {
        'quality_issues': quality_issues,
        'anomalies': anomalies,
        'reconciliations': reconciliations,
        'critical_count': critical_count,
        'warning_count': warning_count,
        'resolved_count': resolved_count,
    })

@login_required
def intelligence_view(request):
    """AI Data Understanding & Automated Business Intelligence Insights."""
    workspace = request.workspace
    datasets = Dataset.objects.filter(workspace=workspace)
    selected_dataset_id = request.GET.get('dataset_id')
    selected_dataset = datasets.filter(id=selected_dataset_id).first() if selected_dataset_id else datasets.first()

    assessments = []
    columns = []
    insights = []

    if selected_dataset and selected_dataset.active_version:
        v = selected_dataset.active_version
        columns = v.columns.all()
        assessments = UnderstandingAssessment.objects.filter(version=v)

        try:
            df = load_version_dataframe(v)
            # Generate empirical automated data insights
            meas_cols = [c.name for c in columns if c.inferred_role in ['currency', 'measure', 'quantity'] or c.data_type in ['integer', 'decimal']]
            cat_cols = [c.name for c in columns if c.inferred_role in ['dimension', 'category', 'status']]
            
            for mc in meas_cols[:3]:
                s = pd.to_numeric(df[mc].astype(str).str.replace(r'[\$,₹€£\s,()]', '', regex=True), errors='coerce').dropna()
                if len(s) > 0:
                    insights.append({
                        'type': 'metric',
                        'title': f"Dominant Volume for {mc.replace('_', ' ').title()}",
                        'text': f"Total sum is {round(float(s.sum()), 2):,} across {len(s)} records, with average ticket of {round(float(s.mean()), 2):,}.",
                        'confidence': '95%'
                    })

            for cc in cat_cols[:2]:
                top = df[cc].value_counts().head(1)
                if len(top) > 0:
                    top_name = top.index[0]
                    top_share = round((top.values[0] / len(df)) * 100, 1)
                    insights.append({
                        'type': 'dimension',
                        'title': f"High Category Concentration: {cc.replace('_', ' ').title()}",
                        'text': f"Leading category is '{top_name}' representing {top_share}% of all activity ({top.values[0]} records).",
                        'confidence': '98%'
                    })
        except Exception:
            pass

    return render(request, 'dashboards/intelligence.html', {
        'datasets': datasets,
        'selected_dataset': selected_dataset,
        'columns': columns,
        'assessments': assessments,
        'insights': insights,
    })

@login_required
def data_overview_view(request):
    """Detailed structural overview of dataset columns, profiling statistics, and raw samples."""
    workspace = request.workspace
    datasets = Dataset.objects.filter(workspace=workspace)
    selected_dataset_id = request.GET.get('dataset_id')
    selected_dataset = datasets.filter(id=selected_dataset_id).first() if selected_dataset_id else datasets.first()

    columns = []
    preview_rows = []
    total_rows = 0

    if selected_dataset and selected_dataset.active_version:
        v = selected_dataset.active_version
        columns = v.columns.all().select_related('profile')
        total_rows = v.row_count
        try:
            df = load_version_dataframe(v)
            preview_rows = df.head(50).replace({float('nan'): None}).to_dict(orient='records')
        except Exception:
            pass

    return render(request, 'dashboards/data_overview.html', {
        'datasets': datasets,
        'selected_dataset': selected_dataset,
        'columns': columns,
        'preview_rows': preview_rows,
        'total_rows': total_rows,
    })

@login_required
def analytics_view(request):
    """Deep-dive multi-dimensional analytical charts and interactive slice & dice."""
    workspace = request.workspace
    datasets = Dataset.objects.filter(workspace=workspace)
    selected_dataset = datasets.first()

    chart_payload = None
    trend_payload = None
    breakdown_table = []
    dim_cols = []
    meas_cols = []
    active_dim = request.GET.get('dim')
    active_meas = request.GET.get('meas')

    if selected_dataset and selected_dataset.active_version:
        v = selected_dataset.active_version
        cols = v.columns.all()
        dim_cols = [c.name for c in cols if c.inferred_role in ['dimension', 'category', 'status'] or c.data_type == 'category']
        meas_cols = [c.name for c in cols if c.inferred_role in ['currency', 'measure', 'quantity'] or c.data_type in ['integer', 'decimal']]

        if not active_dim and dim_cols:
            active_dim = dim_cols[0]
        if not active_meas and meas_cols:
            active_meas = meas_cols[0]

        try:
            df = load_version_dataframe(v)
            if active_dim in df.columns and active_meas in df.columns:
                df_calc = df.copy()
                df_calc['__m'] = clean_numeric_series(df_calc[active_meas])
                
                # Breakdown by selected dimension
                grp = df_calc.groupby(active_dim)['__m'].agg(['sum', 'mean', 'count']).sort_values(by='sum', ascending=False).head(10)
                chart_payload = {
                    'labels': [str(k) for k in grp.index],
                    'values': [round(float(val), 2) for val in grp['sum'].values],
                    'title': f"{active_meas.replace('_', ' ').title()} by {active_dim.replace('_', ' ').title()}"
                }

                for idx, row in grp.iterrows():
                    breakdown_table.append({
                        'category': str(idx),
                        'sum': f"{round(float(row['sum']), 2):,}",
                        'avg': f"{round(float(row['mean']), 2):,}",
                        'count': int(row['count'])
                    })

                # Trend by Date if date column exists
                date_cols = [c.name for c in cols if c.inferred_role == 'date' or 'date' in c.name.lower()]
                if date_cols:
                    d_col = date_cols[0]
                    df_calc['__d'] = pd.to_datetime(df_calc[d_col], errors='coerce')
                    t_grp = df_calc.dropna(subset=['__d']).groupby(df_calc['__d'].dt.strftime('%Y-%m-%d'))['__m'].sum().sort_index().tail(15)
                    trend_payload = {
                        'labels': [str(k) for k in t_grp.index],
                        'values': [round(float(val), 2) for val in t_grp.values],
                        'title': f"{active_meas.replace('_', ' ').title()} Trend"
                    }
        except Exception:
            pass

    return render(request, 'dashboards/analytics.html', {
        'datasets': datasets,
        'selected_dataset': selected_dataset,
        'dim_cols': dim_cols,
        'meas_cols': meas_cols,
        'active_dim': active_dim,
        'active_meas': active_meas,
        'chart_payload': chart_payload,
        'trend_payload': trend_payload,
        'breakdown_table': breakdown_table,
    })

def _compute_period_report(request, grain_name, date_format_str):
    """Core helper for Daily, Weekly, Monthly, and Yearly MIS Reports."""
    workspace = request.workspace
    datasets = Dataset.objects.filter(workspace=workspace)
    selected_dataset = datasets.first()

    period_rows = []
    chart_payload = None
    total_val = 0.0
    total_count = 0
    date_col = None
    meas_col = None

    if selected_dataset and selected_dataset.active_version:
        v = selected_dataset.active_version
        cols = v.columns.all()
        date_candidates = [c.name for c in cols if c.inferred_role == 'date' or 'date' in c.name.lower()]
        meas_candidates = [c.name for c in cols if c.inferred_role in ['currency', 'measure', 'quantity'] or c.data_type in ['integer', 'decimal']]

        if date_candidates and meas_candidates:
            date_col = date_candidates[0]
            meas_col = meas_candidates[0]
            try:
                df = load_version_dataframe(v)
                df_calc = df.copy()
                df_calc['__dt'] = pd.to_datetime(df_calc[date_col], errors='coerce')
                df_calc['__num'] = clean_numeric_series(df_calc[meas_col])
                df_calc = df_calc.dropna(subset=['__dt', '__num'])

                df_calc['__period'] = df_calc['__dt'].dt.strftime(date_format_str)
                grouped = df_calc.groupby('__period').agg(
                    total_sum=('__num', 'sum'),
                    avg_val=('__num', 'mean'),
                    record_count=('__num', 'count')
                ).sort_index()

                prev_val = None
                for period_label, r in grouped.iterrows():
                    val = float(r['total_sum'])
                    growth = None
                    if prev_val is not None and prev_val != 0:
                        growth = round(((val - prev_val) / abs(prev_val)) * 100, 1)
                    prev_val = val

                    period_rows.append({
                        'period': str(period_label),
                        'sum': f"{round(val, 2):,}",
                        'avg': f"{round(float(r['avg_val']), 2):,}",
                        'count': int(r['record_count']),
                        'growth': growth
                    })

                total_val = round(float(grouped['total_sum'].sum()), 2)
                total_count = int(grouped['record_count'].sum())

                chart_payload = {
                    'labels': [str(k) for k in grouped.index],
                    'values': [round(float(v), 2) for v in grouped['total_sum'].values],
                    'title': f"{grain_name} {meas_col.replace('_', ' ').title()}"
                }
            except Exception:
                pass

    return {
        'grain_name': grain_name,
        'selected_dataset': selected_dataset,
        'date_col': date_col,
        'meas_col': meas_col,
        'period_rows': period_rows,
        'total_val': f"{total_val:,}",
        'total_count': total_count,
        'chart_payload': chart_payload,
    }

@login_required
def daily_report_view(request):
    ctx = _compute_period_report(request, "Daily MIS Report", "%Y-%m-%d")
    return render(request, 'dashboards/period_report.html', ctx)

@login_required
def weekly_report_view(request):
    ctx = _compute_period_report(request, "Weekly MIS Report", "%Y-W%W")
    return render(request, 'dashboards/period_report.html', ctx)

@login_required
def monthly_report_view(request):
    ctx = _compute_period_report(request, "Monthly MIS Report", "%Y-%m")
    return render(request, 'dashboards/period_report.html', ctx)

@login_required
def yearly_report_view(request):
    ctx = _compute_period_report(request, "Yearly MIS Report", "%Y")
    return render(request, 'dashboards/period_report.html', ctx)

@login_required
def search_filter_view(request):
    """Multi-column search and dynamic filtering interface."""
    workspace = request.workspace
    datasets = Dataset.objects.filter(workspace=workspace)
    selected_dataset = datasets.first()

    query = request.GET.get('q', '').strip()
    filter_col = request.GET.get('col', '')
    filter_val = request.GET.get('val', '').strip()

    columns = []
    filtered_rows = []
    total_count = 0
    matched_count = 0

    if selected_dataset and selected_dataset.active_version:
        v = selected_dataset.active_version
        columns = [c.name for c in v.columns.all()]
        try:
            df = load_version_dataframe(v)
            total_count = len(df)
            df_filtered = df.copy()

            if query:
                # Text search across all columns
                mask = df_filtered.astype(str).apply(lambda row: row.str.contains(query, case=False, na=False).any(), axis=1)
                df_filtered = df_filtered[mask]

            if filter_col and filter_val and filter_col in df_filtered.columns:
                df_filtered = df_filtered[df_filtered[filter_col].astype(str).str.contains(filter_val, case=False, na=False)]

            matched_count = len(df_filtered)

            # Export to CSV if requested
            if request.GET.get('export') == 'csv':
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = f'attachment; filename="filtered_{selected_dataset.name}.csv"'
                df_filtered.to_csv(path_or_buf=response, index=False)
                return response

            filtered_rows = df_filtered.head(100).replace({float('nan'): None}).to_dict(orient='records')
        except Exception:
            pass

    return render(request, 'dashboards/search_filter.html', {
        'selected_dataset': selected_dataset,
        'columns': columns,
        'filtered_rows': filtered_rows,
        'total_count': total_count,
        'matched_count': matched_count,
        'query': query,
        'filter_col': filter_col,
        'filter_val': filter_val,
    })

@login_required
def pivot_table_view(request):
    """Dynamic multi-dimensional Pivot Table cross-tabulation engine."""
    workspace = request.workspace
    datasets = Dataset.objects.filter(workspace=workspace)
    selected_dataset = datasets.first()

    row_col = request.GET.get('row')
    col_col = request.GET.get('col')
    val_col = request.GET.get('val')
    agg_func = request.GET.get('agg', 'sum')

    columns = []
    cat_cols = []
    num_cols = []
    pivot_html = ""
    error_msg = ""

    if selected_dataset and selected_dataset.active_version:
        v = selected_dataset.active_version
        cols = v.columns.all()
        cat_cols = [c.name for c in cols if c.inferred_role in ['dimension', 'category', 'status'] or c.data_type in ['string', 'category']]
        num_cols = [c.name for c in cols if c.inferred_role in ['currency', 'measure', 'quantity'] or c.data_type in ['integer', 'decimal']]

        # Default selections
        if not row_col and cat_cols:
            row_col = cat_cols[0]
        if not col_col and len(cat_cols) > 1:
            col_col = cat_cols[1]
        elif not col_col and cat_cols:
            col_col = cat_cols[0]
        if not val_col and num_cols:
            val_col = num_cols[0]

        try:
            df = load_version_dataframe(v)
            if row_col in df.columns and col_col in df.columns and val_col in df.columns:
                df_calc = df.copy()
                df_calc['__v'] = clean_numeric_series(df_calc[val_col])
                
                pivot = pd.pivot_table(
                    df_calc,
                    index=row_col,
                    columns=col_col,
                    values='__v',
                    aggfunc=agg_func,
                    fill_value=0,
                    margins=True,
                    margins_name='Grand Total'
                )

                # Export to CSV if requested
                if request.GET.get('export') == 'csv':
                    response = HttpResponse(content_type='text/csv')
                    response['Content-Disposition'] = f'attachment; filename="pivot_{row_col}_{col_col}.csv"'
                    pivot.to_csv(path_or_buf=response)
                    return response

                # Format values
                formatted_pivot = pivot.map(lambda x: f"{round(float(x), 2):,}" if pd.notnull(x) else "-")
                pivot_html = formatted_pivot.to_html(classes="data-table", justify="left")
        except Exception as e:
            error_msg = str(e)

    return render(request, 'dashboards/pivot_table.html', {
        'selected_dataset': selected_dataset,
        'cat_cols': cat_cols,
        'num_cols': num_cols,
        'row_col': row_col,
        'col_col': col_col,
        'val_col': val_col,
        'agg_func': agg_func,
        'pivot_html': pivot_html,
        'error_msg': error_msg,
    })

@login_required
def report_history_view(request):
    """Archival history and audit repository of all generated MIS Reports."""
    workspace = request.workspace
    report_runs = ReportRun.objects.filter(report_definition__workspace=workspace).order_by('-generated_at')
    return render(request, 'dashboards/report_history.html', {
        'report_runs': report_runs,
    })

@login_required
def export_hub_view(request):
    """Centralized download and export station for datasets, MIS reports, and audits."""
    workspace = request.workspace
    datasets = Dataset.objects.filter(workspace=workspace)
    report_runs = ReportRun.objects.filter(report_definition__workspace=workspace).order_by('-generated_at')[:20]
    return render(request, 'dashboards/export_hub.html', {
        'datasets': datasets,
        'report_runs': report_runs,
    })

@login_required
def help_view(request):
    """In-app documentation, user guide, formula directory, and FAQ."""
    return render(request, 'dashboards/help.html')

