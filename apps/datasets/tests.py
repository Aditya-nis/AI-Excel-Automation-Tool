import io
import pandas as pd
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.datasets.models import Dataset, DatasetVersion, SourceFile
from apps.datasets.services import save_source_file, ingest_file_to_dataset, load_version_dataframe

User = get_user_model()

class DatasetPipelineTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='analyst1', password='password123')
        self.workspace = Workspace.objects.create(name='Finance Workspace', owner=self.user)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.user, role='admin')

    def test_csv_upload_and_ingestion(self):
        csv_content = b"order_id,product,amount,order_date,status\n101,Laptop,1200.50,2026-01-15,Completed\n102,Mouse,25.00,2026-01-16,Pending\n103,Keyboard,,2026-01-17,Completed\n"
        upload = SimpleUploadedFile("orders.csv", csv_content, content_type="text/csv")

        source_file = save_source_file(upload, self.workspace, self.user)
        self.assertEqual(source_file.filename, "orders.csv")
        self.assertTrue(len(source_file.sha256_hash) > 0)

        dataset, version = ingest_file_to_dataset(source_file, user=self.user)
        self.assertEqual(dataset.name, "orders")
        self.assertEqual(version.version_number, 1)
        self.assertEqual(version.row_count, 3)
        self.assertEqual(version.column_count, 5)

        # Verify DataFrame is loaded correctly from immutable Parquet
        df = load_version_dataframe(version)
        self.assertEqual(len(df), 3)
        self.assertIn('amount', df.columns)

        # Verify quality score was calculated
        self.assertIsNotNone(version.quality_score)
        self.assertTrue(version.columns.count() == 5)
