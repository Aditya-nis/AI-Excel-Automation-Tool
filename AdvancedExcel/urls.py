from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.accounts.views import login_view, register_view, logout_view, password_change_view
from apps.dashboards.views import (
    dashboard_home, upload_view, dataset_detail_view,
    understanding_view, data_quality_view, transformations_view,
    consolidation_view, semantic_models_view, ask_data_view,
    reports_view, automation_view, jobs_view, audit_view, settings_view,
    anomalies_view, notifications_view, approvals_view, visual_workflow_builder,
    mis_home_view, exception_center_view, intelligence_view, data_overview_view,
    analytics_view, daily_report_view, weekly_report_view, monthly_report_view, yearly_report_view,
    search_filter_view, pivot_table_view, report_history_view, export_hub_view, help_view
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentication
    path('accounts/login/', login_view, name='login'),
    path('accounts/register/', register_view, name='register'),
    path('accounts/logout/', logout_view, name='logout'),
    path('accounts/password-change/', password_change_view, name='password_change'),

    # REST APIs
    path('api/', include('apps.api.urls')),

    # 21 Core App Features Matching Navigation
    path('', mis_home_view, name='mis_home'),
    path('mis/', mis_home_view, name='mis_home_alt'),
    path('dashboard/', dashboard_home, name='dashboard'),
    path('reports/', reports_view, name='reports'),
    path('exceptions/', exception_center_view, name='exception_center'),
    path('ask-ai/', ask_data_view, name='ask_ai'),
    path('ask-data/', ask_data_view, name='ask_data'),
    path('intelligence/', intelligence_view, name='intelligence'),
    path('upload/', upload_view, name='upload'),
    path('overview/', data_overview_view, name='data_overview'),
    path('analytics/', analytics_view, name='analytics'),
    path('reports/daily/', daily_report_view, name='daily_report'),
    path('reports/weekly/', weekly_report_view, name='weekly_report'),
    path('reports/monthly/', monthly_report_view, name='monthly_report'),
    path('reports/yearly/', yearly_report_view, name='yearly_report'),
    path('search-filter/', search_filter_view, name='search_filter'),
    path('pivot-table/', pivot_table_view, name='pivot_table'),
    path('quality/', data_quality_view, name='data_quality_center'),
    path('reports/history/', report_history_view, name='report_history'),
    path('automation/log/', jobs_view, name='automation_log'),
    path('jobs/', jobs_view, name='jobs'),
    path('export/', export_hub_view, name='export_hub'),
    path('settings/', settings_view, name='settings'),
    path('help/', help_view, name='help'),

    # Deep-dive Management Routes
    path('datasets/<int:dataset_id>/', dataset_detail_view, name='dataset_detail'),
    path('datasets/<int:dataset_id>/understanding/', understanding_view, name='understanding'),
    path('datasets/<int:dataset_id>/quality/', data_quality_view, name='data_quality'),
    path('datasets/<int:dataset_id>/transformations/', transformations_view, name='transformations'),
    path('consolidation/', consolidation_view, name='consolidation'),
    path('semantic-models/', semantic_models_view, name='semantic_models'),
    path('automation/', automation_view, name='automation'),
    path('automation/builder/', visual_workflow_builder, name='visual_workflow_builder'),
    path('anomalies/', anomalies_view, name='anomalies'),
    path('notifications/', notifications_view, name='notifications'),
    path('approvals/', approvals_view, name='approvals'),
    path('audit/', audit_view, name='audit'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
