from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.api.views import (
    WorkspaceViewSet, FileViewSet, DatasetViewSet, QualityViewSet,
    UnderstandingViewSet, CleaningViewSet, ConsolidationViewSet,
    SemanticModelViewSet, AskDataViewSet, ReportViewSet,
    AutomationViewSet, JobViewSet, AuditViewSet,
    AnomalyViewSet, NotificationViewSet, ApprovalViewSet
)

router = DefaultRouter()
router.register(r'workspaces', WorkspaceViewSet, basename='workspaces')
router.register(r'files', FileViewSet, basename='files')
router.register(r'datasets', DatasetViewSet, basename='datasets')
router.register(r'quality', QualityViewSet, basename='quality')
router.register(r'understanding', UnderstandingViewSet, basename='understanding')
router.register(r'cleaning', CleaningViewSet, basename='cleaning')
router.register(r'consolidation', ConsolidationViewSet, basename='consolidation')
router.register(r'semantic-models', SemanticModelViewSet, basename='semantic-models')
router.register(r'ask-data', AskDataViewSet, basename='ask-data')
router.register(r'reports', ReportViewSet, basename='reports')
router.register(r'automation', AutomationViewSet, basename='automation')
router.register(r'jobs', JobViewSet, basename='jobs')
router.register(r'audit', AuditViewSet, basename='audit')
router.register(r'anomalies', AnomalyViewSet, basename='anomalies')
router.register(r'notifications', NotificationViewSet, basename='notifications')
router.register(r'approvals', ApprovalViewSet, basename='approvals')

urlpatterns = [
    path('v1/', include(router.urls)),
]
