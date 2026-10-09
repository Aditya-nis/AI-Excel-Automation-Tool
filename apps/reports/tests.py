import os
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.datasets.services import save_source_file, ingest_file_to_dataset
from apps.reports.models import ReportDefinition
from apps.reports.services import generate_mis_report

User = get_user_model()

class MisReportsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='reporter1', password='password123')
        self.workspace = Workspace.objects.create(name='Reports WS', owner=self.user)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.user, role='admin')

        csv_content = (
            b"date,region,sales,units\n"
            b"2026-01-01,North,1000,10\n"
            b"2026-01-02,South,2000,20\n"
            b"2026-01-03,North,1500,15\n"
        )
        upload = SimpleUploadedFile("sales.csv", csv_content, content_type="text/csv")
        source = save_source_file(upload, self.workspace, self.user)
        self.dataset, _ = ingest_file_to_dataset(source, user=self.user)

    def test_mis_report_generation_and_exports(self):
        report_def = ReportDefinition.objects.create(
            workspace=self.workspace,
            name="Executive Sales MIS",
            report_type="sales_mis",
            dataset=self.dataset,
            date_column="date",
            metric_columns=["sales", "units"],
            dimension_columns=["region"],
            created_by=self.user
        )

        run = generate_mis_report(report_def, user=self.user)
        self.assertIsNotNone(run)
        self.assertIn("sales", run.summary_kpis)
        self.assertEqual(run.summary_kpis["sales"]["total"], 4500.0)

        # Check export files generated
        self.assertTrue(os.path.exists(run.excel_export_path))
        self.assertTrue(os.path.exists(run.csv_export_path))
        if run.pdf_export_path:
            self.assertTrue(os.path.exists(run.pdf_export_path))
