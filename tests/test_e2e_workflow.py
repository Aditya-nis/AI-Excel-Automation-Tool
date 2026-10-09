import os
import shutil
from decimal import Decimal
import pandas as pd
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.datasets.models import SourceFile, Dataset, DatasetVersion
from apps.datasets.services import save_source_file, ingest_file_to_dataset, load_version_dataframe
from apps.cleaning.services import execute_transformations
from apps.reports.models import ReportDefinition
from apps.reports.services import generate_mis_report
from apps.ask_data.services import compile_and_execute_query
from apps.audit.models import AuditEvent

User = get_user_model()

class EndToEndBusinessWorkflowTests(TestCase):
    """End-to-End Business Integration Tests: Ingestion -> Profiling -> Cleaning -> MIS Report -> Audit."""

    def setUp(self):
        self.user = User.objects.create_user(username='cfo_user', password='password123')
        self.workspace = Workspace.objects.create(name='Global Finance Corp', owner=self.user)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.user, role='owner')

        self.client = Client()
        self.client.login(username='cfo_user', password='password123')

    def test_complete_end_to_end_business_pipeline(self):
        """Validates the full enterprise analytics lifecycle from raw file to executive MIS report."""
        # Step 1: Prepare synthetic enterprise CSV data with whitespace, currency, and accounting negatives
        csv_content = (
            "date,region,category,sales_amount,units\n"
            "2026-01-15, North ,Enterprise,$1000.50,10\n"
            "2026-01-16, South ,Enterprise,  (250.00)  ,2\n"
            "2026-01-17, North ,SMB,$500.00,5\n"
            "2026-01-18, East  ,SMB,$1500.25,15\n"
            "2026-01-18, East  ,SMB,$1500.25,15\n"  # Duplicate row
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("q1_sales.csv", csv_content, content_type="text/csv")

        # Step 2: Upload source file
        source_file = save_source_file(uploaded, self.workspace, self.user)
        self.assertIsNotNone(source_file.id)
        self.assertEqual(source_file.filename, "q1_sales.csv")

        # Step 3: Ingest into primary Dataset and Version 1
        dataset, version1 = ingest_file_to_dataset(source_file, user=self.user)
        self.assertEqual(dataset.active_version, version1)
        self.assertEqual(version1.version_number, 1)
        self.assertEqual(version1.row_count, 5)

        # Step 4: Verify initial raw data loaded correctly
        df_v1 = load_version_dataframe(version1)
        self.assertEqual(len(df_v1), 5)

        # Step 5: Apply Cleaning Pipeline (Deduplicate, Trim Whitespace, Convert Numeric Currency with Negatives)
        steps = [
            {'operation_type': 'remove_duplicates', 'parameters': {'keep': 'first'}},
            {'operation_type': 'trim_whitespace', 'column_name': 'region'},
            {'operation_type': 'convert_type', 'column_name': 'sales_amount', 'parameters': {'target_type': 'numeric'}}
        ]
        version2 = execute_transformations(dataset, steps, user=self.user)
        self.assertEqual(version2.version_number, 2)
        self.assertEqual(version2.row_count, 4)  # Duplicate removed
        self.assertEqual(dataset.active_version, version2)

        # Step 6: Verify Immutability (Version 1 has 5 rows, Version 2 has 4 rows)
        df_v1_recheck = load_version_dataframe(version1)
        df_v2 = load_version_dataframe(version2)
        self.assertEqual(len(df_v1_recheck), 5)
        self.assertEqual(len(df_v2), 4)

        # Verify negative number preserved in Version 2: (250.00) -> -250.00
        self.assertEqual(df_v2.loc[df_v2['date'] == '2026-01-16', 'sales_amount'].values[0], -250.00)
        # Verify regions trimmed
        self.assertEqual(df_v2.loc[df_v2['date'] == '2026-01-15', 'region'].values[0], "North")

        # Step 7: Create and Generate Executive MIS Report
        report_def = ReportDefinition.objects.create(
            workspace=self.workspace,
            dataset=dataset,
            name="Q1 Executive Financial Summary",
            report_type="monthly",
            date_column="date",
            metric_columns=["sales_amount", "units"],
            dimension_columns=["region", "category"],
            created_by=self.user
        )

        run = generate_mis_report(report_def, user=self.user)
        self.assertIsNotNone(run.id)
        self.assertIn("sales_amount", run.summary_kpis)
        
        # Expected sum: 1000.50 + (-250.00) + 500.00 + 1500.25 = 2750.75
        expected_total = 2750.75
        self.assertEqual(run.summary_kpis['sales_amount']['total'], expected_total)
        self.assertEqual(run.summary_kpis['sales_amount']['count'], 4)

        # Step 8: Verify Export Artifacts Exist on Disk
        self.assertTrue(os.path.exists(run.excel_export_path))
        self.assertTrue(os.path.exists(run.csv_export_path))

        # Step 9: Ask-Your-Data Natural Language Query Execution
        nl_result = compile_and_execute_query(dataset, "total sales amount by region")
        self.assertIsNotNone(nl_result)
        self.assertIn("headers", nl_result['result_data']['table'])
        self.assertGreater(len(nl_result['result_data']['table']['rows']), 0)

        # Step 10: Validate Audit Trail Integrity
        audits = AuditEvent.objects.filter(workspace=self.workspace)
        self.assertGreater(audits.count(), 0)
        event_types = list(audits.values_list('event_type', flat=True))
        self.assertIn("file.upload", event_types)
        self.assertIn("dataset.transformed", event_types)
        self.assertIn("report.generate", event_types)
