from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.approvals.models import ApprovalRequest
from apps.approvals.services import request_approval, decide_approval

User = get_user_model()

class ApprovalWorkflowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='admin_boss', password='password123')
        self.requester = User.objects.create_user(username='analyst_user', password='password123')
        self.workspace = Workspace.objects.create(name='Audit Workspace', owner=self.owner)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.owner, role='admin')
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.requester, role='analyst')

    def test_request_and_decide_approval(self):
        # 1. Create approval request
        req = request_approval(
            workspace=self.workspace,
            requester=self.requester,
            request_type='report_publication',
            title='Publish Q1 Board MIS Report',
            description='Executive quarterly financial balance sheet ready for release.',
            target_type='ReportDefinition',
            target_id='10'
        )
        self.assertEqual(req.status, 'pending')
        self.assertEqual(req.requester, self.requester)

        # 2. Decision: Approve
        decided = decide_approval(req, reviewer=self.owner, action='approved', comments='Audited and verified.')
        self.assertEqual(decided.status, 'approved')
        self.assertEqual(decided.reviewed_by, self.owner)
        self.assertIsNotNone(decided.reviewed_at)
        self.assertEqual(decided.review_comments, 'Audited and verified.')
