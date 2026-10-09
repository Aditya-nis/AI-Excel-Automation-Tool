from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.datasets.services import save_source_file, ingest_file_to_dataset
from apps.cleaning.models import CleaningRecipe
from apps.automation.models import WorkflowSchedule
from apps.automation.services import detect_schema_drift, run_workflow_job

User = get_user_model()

class AutomationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='automator', password='password123')
        self.workspace = Workspace.objects.create(name='Automated WS', owner=self.user)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.user, role='admin')

        csv_content = b"region,sales,units\nNorth,500,10\nSouth,600,12\n"
        upload = SimpleUploadedFile("monthly_sales.csv", csv_content, content_type="text/csv")
        source = save_source_file(upload, self.workspace, self.user)
        self.dataset, _ = ingest_file_to_dataset(source, user=self.user)

        self.recipe = CleaningRecipe.objects.create(
            workspace=self.workspace,
            name="Sales Standardizer",
            target_schema={'columns': ['region', 'sales', 'units']},
            steps_config=[{'operation_type': 'change_case', 'column_name': 'region', 'parameters': {'case_type': 'upper'}}],
            created_by=self.user
        )

    def test_schema_drift_detection(self):
        # 1. Matching schema -> No drift
        has_drift, _ = detect_schema_drift(self.recipe.target_schema, ['region', 'sales', 'units'])
        self.assertFalse(has_drift)

        # 2. Missing required column 'units' -> Drift detected!
        drift_detected, details = detect_schema_drift(self.recipe.target_schema, ['region', 'sales'])
        self.assertTrue(drift_detected)
        self.assertIn('units', details['missing_required_columns'])

    def test_workflow_execution_and_drift_safeguard(self):
        wf = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Monthly Sales Workflow",
            dataset=self.dataset,
            cleaning_recipe=self.recipe,
            cron_expression="0 6 1 * *",
            stop_on_drift=True,
            created_by=self.user
        )

        # Run with current dataset -> Success
        job = run_workflow_job(wf, trigger_type='manual', user=self.user)
        self.assertEqual(job.status, 'completed')
        self.assertFalse(job.schema_drift_detected)

        # Now simulate drift by requiring an absent column in recipe
        self.recipe.target_schema = {'columns': ['region', 'sales', 'units', 'missing_fiscal_year_col']}
        self.recipe.save()

        # Run again -> Must halt and flag drift_detected!
        job_drift = run_workflow_job(wf, trigger_type='manual', user=self.user)
        self.assertEqual(job_drift.status, 'drift_detected')
        self.assertTrue(job_drift.schema_drift_detected)
        self.assertIn("HALTED: Schema drift detected", job_drift.execution_logs)
