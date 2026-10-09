from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.datasets.services import save_source_file, ingest_file_to_dataset
from apps.ask_data.models import ChatSession
from apps.ask_data.services import handle_user_query

User = get_user_model()

class AskDataTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='asker1', password='password123')
        self.workspace = Workspace.objects.create(name='AskData WS', owner=self.user)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.user, role='admin')

        csv_content = (
            b"region,sales,category\n"
            b"North,500,Electronics\n"
            b"North,300,Furniture\n"
            b"South,700,Electronics\n"
            b"South,100,Furniture\n"
        )
        upload = SimpleUploadedFile("regional_sales.csv", csv_content, content_type="text/csv")
        source = save_source_file(upload, self.workspace, self.user)
        self.dataset, _ = ingest_file_to_dataset(source, user=self.user)

        self.session = ChatSession.objects.create(
            workspace=self.workspace,
            dataset=self.dataset,
            title="Q&A Session",
            user=self.user
        )

    def test_ask_data_total_measure(self):
        query_run = handle_user_query(self.session, "What is the total sales?", user=self.user)
        self.assertIsNotNone(query_run)
        res_data = query_run.result_data
        # 500 + 300 + 700 + 100 = 1600
        self.assertEqual(res_data['table']['rows'][0][0], 1600.0)

    def test_ask_data_grouped_by_dimension(self):
        query_run = handle_user_query(self.session, "Show sales by region", user=self.user)
        self.assertIsNotNone(query_run)
        res_data = query_run.result_data
        self.assertIn('chart', res_data)
        self.assertIn('labels', res_data['chart'])
        # North and South
        self.assertEqual(len(res_data['chart']['labels']), 2)
