from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.datasets.models import Dataset, DatasetVersion, DatasetColumn
from apps.datasets.services import get_storage_path
import pandas as pd
import os

User = get_user_model()

class NavigationAndFeatureViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='test_admin', password='Password123!')
        self.workspace = Workspace.objects.create(name='Test Workspace', owner=self.user)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.user, role='admin')
        
        self.client = Client()
        self.client.login(username='test_admin', password='Password123!')

        # Set session workspace
        session = self.client.session
        session['active_workspace_id'] = self.workspace.id
        session.save()

        # Seed test dataset
        self.dataset = Dataset.objects.create(workspace=self.workspace, name='Sales Q1')
        storage_path = get_storage_path(self.dataset.id, 1)

        df = pd.DataFrame({
            'Date': ['2026-01-01', '2026-01-02', '2026-02-01', '2026-02-15'],
            'Region': ['North', 'South', 'North', 'East'],
            'Category': ['Hardware', 'Software', 'Hardware', 'Services'],
            'Revenue': [1500.0, 2200.0, 1800.0, 3100.0],
            'Units': [10, 15, 12, 20]
        })
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)
        df.to_parquet(storage_path, index=False)

        self.version = DatasetVersion.objects.create(
            dataset=self.dataset,
            version_number=1,
            row_count=4,
            column_count=5,
            file_path=storage_path
        )
        self.dataset.active_version = self.version
        self.dataset.save()

        DatasetColumn.objects.create(version=self.version, name='Date', data_type='date', inferred_role='date', ordinal_position=0)
        DatasetColumn.objects.create(version=self.version, name='Region', data_type='string', inferred_role='dimension', ordinal_position=1)
        DatasetColumn.objects.create(version=self.version, name='Category', data_type='string', inferred_role='dimension', ordinal_position=2)
        DatasetColumn.objects.create(version=self.version, name='Revenue', data_type='decimal', inferred_role='currency', ordinal_position=3)
        DatasetColumn.objects.create(version=self.version, name='Units', data_type='integer', inferred_role='measure', ordinal_position=4)

    def tearDown(self):
        if hasattr(self, 'version') and os.path.exists(self.version.file_path):
            os.remove(self.version.file_path)

    def test_mis_home_renders(self):
        res = self.client.get(reverse('mis_home'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "MIS Executive Home")

    def test_dashboard_renders(self):
        res = self.client.get(reverse('dashboard'))
        self.assertEqual(res.status_code, 200)

    def test_exception_center_renders(self):
        res = self.client.get(reverse('exception_center'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Exception Center")

    def test_intelligence_renders(self):
        res = self.client.get(reverse('intelligence'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "AI Data Intelligence")

    def test_data_overview_renders(self):
        res = self.client.get(reverse('data_overview'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Data Overview")

    def test_analytics_renders(self):
        res = self.client.get(reverse('analytics'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Multi-Dimensional Analytics")

    def test_periodic_reports_render(self):
        for route in ['daily_report', 'weekly_report', 'monthly_report', 'yearly_report']:
            res = self.client.get(reverse(route))
            self.assertEqual(res.status_code, 200)

    def test_search_filter_and_export(self):
        res = self.client.get(reverse('search_filter') + '?q=North')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "North")

        csv_res = self.client.get(reverse('search_filter') + '?q=North&export=csv')
        self.assertEqual(csv_res.status_code, 200)
        self.assertEqual(csv_res['Content-Type'], 'text/csv')

    def test_pivot_table_and_export(self):
        res = self.client.get(reverse('pivot_table') + '?row=Region&col=Category&val=Revenue&agg=sum')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Pivot Table")
        self.assertContains(res, "Grand Total")

        csv_res = self.client.get(reverse('pivot_table') + '?row=Region&col=Category&val=Revenue&agg=sum&export=csv')
        self.assertEqual(csv_res.status_code, 200)
        self.assertEqual(csv_res['Content-Type'], 'text/csv')

    def test_report_history_renders(self):
        res = self.client.get(reverse('report_history'))
        self.assertEqual(res.status_code, 200)

    def test_export_hub_renders(self):
        res = self.client.get(reverse('export_hub'))
        self.assertEqual(res.status_code, 200)

    def test_help_renders(self):
        res = self.client.get(reverse('help'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Help & Operational Guide")
