from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.datasets.services import save_source_file, ingest_file_to_dataset
from apps.consolidation.services import preview_join_cardinality, execute_consolidation, execute_reconciliation

User = get_user_model()

class ConsolidationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='consolidator', password='password123')
        self.workspace = Workspace.objects.create(name='Ops WS', owner=self.user)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.user, role='admin')

        csv1 = b"cust_id,cust_name\n1,Alpha\n2,Beta\n3,Gamma\n"
        csv2 = b"cust_id,order_amount\n1,100\n1,200\n2,300\n"

        u1 = SimpleUploadedFile("customers.csv", csv1, content_type="text/csv")
        u2 = SimpleUploadedFile("orders.csv", csv2, content_type="text/csv")

        s1 = save_source_file(u1, self.workspace, self.user)
        s2 = save_source_file(u2, self.workspace, self.user)

        self.d1, _ = ingest_file_to_dataset(s1, user=self.user)
        self.d2, _ = ingest_file_to_dataset(s2, user=self.user)

    def test_cardinality_preview(self):
        df1 = self.d1.active_version.columns.values()
        from apps.datasets.services import load_version_dataframe
        df1 = load_version_dataframe(self.d1.active_version)
        df2 = load_version_dataframe(self.d2.active_version)

        card = preview_join_cardinality(df1, df2, 'cust_id', 'cust_id')
        # d1 has unique keys (1,2,3), d2 has non-unique keys (1,1,2) -> 1:N
        self.assertEqual(card['cardinality'], '1:N')
        self.assertIn('One-to-many', card['warning'])
        self.assertEqual(card['matched_keys_count'], 2)

    def test_join_consolidation(self):
        merged = execute_consolidation(
            workspace=self.workspace,
            operation_type='join',
            primary_dataset=self.d1,
            secondary_dataset=self.d2,
            params={'primary_key': 'cust_id', 'secondary_key': 'cust_id', 'join_type': 'inner'},
            user=self.user
        )
        self.assertIsNotNone(merged)
        self.assertEqual(merged.active_version.row_count, 3) # (1->100, 1->200, 2->300)

    def test_reconciliation(self):
        recon = execute_reconciliation(
            workspace=self.workspace,
            primary_dataset=self.d1,
            secondary_dataset=self.d2,
            primary_key='cust_id',
            secondary_key='cust_id',
            control_total_col1='cust_id',
            control_total_col2='order_amount',
            tolerance=0.0,
            user=self.user
        )
        self.assertEqual(recon.matched_records_count, 2)
        self.assertEqual(recon.unmatched_primary_count, 1) # Key '3' not in orders
        self.assertFalse(recon.is_reconciled) # Because unmatched rows and sum variance exist
