import os
import pandas as pd
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.datasets.models import Dataset, DatasetVersion, DatasetColumn
from apps.anomalies.models import AnomalyEvent, MetricForecast
from apps.anomalies.services import detect_anomalies_for_dataset, generate_metric_forecast

User = get_user_model()

class AnomalyDetectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='analyst', password='password123')
        self.workspace = Workspace.objects.create(name='Test Workspace', owner=self.user)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.user, role='admin')
        
        from apps.datasets.services import get_storage_path
        self.dataset = Dataset.objects.create(workspace=self.workspace, name='Sales Data')
        storage_path = get_storage_path(self.dataset.id, 1)
        
        # Write test parquet dataframe
        df = pd.DataFrame({
            'Date': [f'2026-01-{i:02d}' for i in range(1, 11)],
            'Revenue': [100.0, 105.0, 102.0, 98.0, 103.0, 101.0, 99.0, 104.0, 102.0, 5000.0] # 5000 is obvious spike
        })
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)
        df.to_parquet(storage_path, index=False)

        self.version = DatasetVersion.objects.create(
            dataset=self.dataset,
            version_number=1,
            row_count=10,
            column_count=2,
            file_path=storage_path
        )
        self.dataset.active_version = self.version
        self.dataset.save()

        DatasetColumn.objects.create(
            version=self.version,
            name='Date',
            data_type='string',
            inferred_role='dimension',
            ordinal_position=0
        )
        DatasetColumn.objects.create(
            version=self.version,
            name='Revenue',
            data_type='decimal',
            inferred_role='currency',
            ordinal_position=1
        )

    def tearDown(self):
        if hasattr(self, 'version') and os.path.exists(self.version.file_path):
            os.remove(self.version.file_path)

    def test_detect_anomalies_finds_spike(self):
        anomalies = detect_anomalies_for_dataset(self.dataset, user=self.user)
        self.assertGreaterEqual(len(anomalies), 1)
        spike = anomalies[0]
        self.assertEqual(spike.metric_name, 'Revenue')
        self.assertEqual(spike.observed_value, 5000.0)
        self.assertIn(spike.severity, ['warning', 'critical'])
        self.assertGreaterEqual(spike.z_score, 2.5)

    def test_generate_metric_forecast(self):
        forecast = generate_metric_forecast(self.dataset, 'Revenue', 'Date', horizon=3, user=self.user)
        self.assertIsNotNone(forecast)
        self.assertEqual(forecast.horizon_periods, 3)
        self.assertEqual(len(forecast.forecast_results), 3)
        self.assertIn('estimate', forecast.forecast_results[0])
        self.assertIn('upper_bound', forecast.forecast_results[0])
