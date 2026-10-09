from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.datasets.services import save_source_file, ingest_file_to_dataset, load_version_dataframe
from apps.cleaning.services import execute_transformations, preview_transformations, undo_transformation, restore_version

User = get_user_model()

class CleaningEngineTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cleaner1', password='password123')
        self.workspace = Workspace.objects.create(name='Cleaning Test WS', owner=self.user)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.user, role='admin')

        # Create dataset with intentional flaws: spaces, duplicate rows, missing value
        csv_content = (
            b"id,customer,amount\n"
            b"1, Alice ,100\n"
            b"2,  Bob  ,200\n"
            b"1, Alice ,100\n" # Duplicate row
            b"3,Charlie,\n"    # Missing amount
        )
        upload = SimpleUploadedFile("dirty.csv", csv_content, content_type="text/csv")
        source = save_source_file(upload, self.workspace, self.user)
        self.dataset, self.v1 = ingest_file_to_dataset(source, user=self.user)

    def test_dry_run_preview(self):
        steps = [
            {'operation_type': 'trim_whitespace', 'column_name': 'customer'},
            {'operation_type': 'remove_duplicates', 'parameters': {'keep': 'first'}}
        ]
        preview = preview_transformations(self.dataset, steps)
        self.assertEqual(preview['total_rows_before'], 4)
        self.assertEqual(preview['total_rows_after'], 3)
        # Verify original dataset active version did not change during dry-run
        self.assertEqual(self.dataset.active_version.version_number, 1)

    def test_transformation_execution_and_undo(self):
        steps = [
            {'operation_type': 'trim_whitespace', 'column_name': 'customer'},
            {'operation_type': 'remove_duplicates', 'parameters': {'keep': 'first'}},
            {'operation_type': 'fill_missing', 'column_name': 'amount', 'parameters': {'strategy': 'literal', 'fill_value': '0'}}
        ]
        v2 = execute_transformations(self.dataset, steps, user=self.user)
        self.assertEqual(v2.version_number, 2)
        self.assertEqual(self.dataset.active_version.id, v2.id)
        self.assertEqual(v2.row_count, 3)

        df_v2 = load_version_dataframe(v2)
        # Verify customers are trimmed
        self.assertEqual(list(df_v2['customer']), ['Alice', 'Bob', 'Charlie'])

        # Test Undo
        restored_v1 = undo_transformation(self.dataset, self.user)
        self.assertEqual(restored_v1.version_number, 1)
        self.assertEqual(self.dataset.active_version.version_number, 1)
        self.assertEqual(self.dataset.active_version.row_count, 4)

        # Test Restore specific version
        restored_v2 = restore_version(self.dataset, 2, self.user)
        self.assertEqual(self.dataset.active_version.version_number, 2)
        self.assertEqual(self.dataset.active_version.row_count, 3)
