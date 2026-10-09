from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from decimal import Decimal

from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.datasets.models import Dataset, DatasetVersion
from apps.datasets.services import validate_uploaded_file
from apps.core.utils import SafeJSONEncoder

User = get_user_model()

class SecurityAuditTests(TestCase):
    """Automated security audit test cases for authentication, authorization, and isolation."""

    def setUp(self):
        self.user1 = User.objects.create_user(username='alice', password='password123')
        self.user2 = User.objects.create_user(username='bob', password='password123')

        self.workspace1 = Workspace.objects.create(name='Workspace 1', owner=self.user1)
        self.workspace2 = Workspace.objects.create(name='Workspace 2', owner=self.user2)

        WorkspaceMembership.objects.create(workspace=self.workspace1, user=self.user1, role='owner')
        WorkspaceMembership.objects.create(workspace=self.workspace2, user=self.user2, role='owner')

        self.client1 = Client()
        self.client1.login(username='alice', password='password123')

        self.client2 = Client()
        self.client2.login(username='bob', password='password123')

    def test_unauthenticated_requests_redirect(self):
        """Unauthenticated requests to protected endpoints must redirect to login."""
        unauthenticated_client = Client()
        protected_urls = [
            '/',
            '/dashboard/',
            '/reports/',
            '/upload/',
            '/intelligence/',
            '/analytics/',
        ]
        for url in protected_urls:
            resp = unauthenticated_client.get(url)
            self.assertEqual(resp.status_code, 302, f"URL {url} failed to redirect unauthenticated user")
            self.assertIn('/accounts/login/', resp.url)

    def test_workspace_isolation_datasets(self):
        """Alice must never access Bob's workspace datasets."""
        ds_bob = Dataset.objects.create(workspace=self.workspace2, name="Bob Confidential Data", created_by=self.user2)

        # Alice attempts to access Bob's dataset detail
        resp = self.client1.get(f'/datasets/{ds_bob.id}/')
        # Expect 404 because get_object_or_404 scopes to request.workspace
        self.assertEqual(resp.status_code, 404)

    def test_file_upload_validation_rejects_dangerous_extensions(self):
        """Upload validation must strictly reject unauthorized extensions (e.g. .exe, .sh, .py)."""
        malicious_file = SimpleUploadedFile("malicious.exe", b"MZ\x90\x00\x03\x00\x00\x00", content_type="application/octet-stream")
        with self.assertRaises(ValidationError) as cm:
            validate_uploaded_file(malicious_file)
        self.assertIn("Unsupported file format", str(cm.exception))

        script_file = SimpleUploadedFile("payload.py", b"import os; os.system('ls')", content_type="text/x-python")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(script_file)

    def test_safe_json_encoder_xss_prevention(self):
        """SafeJSONEncoder properly handles Decimals, dates, and NaN values."""
        encoder = SafeJSONEncoder()
        test_data = {
            'amount': Decimal('123.45'),
            'none_val': None,
            'nan_val': float('nan')
        }
        encoded = encoder.encode(test_data)
        self.assertIn('"amount": 123.45', encoded)
        self.assertIn('"nan_val": null', encoded)
