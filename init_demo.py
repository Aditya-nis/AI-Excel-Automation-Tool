import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AdvancedExcel.settings')
django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from apps.workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
from apps.datasets.services import save_source_file, ingest_file_to_dataset
from apps.semantic_model.services import auto_generate_semantic_model
from apps.reports.models import ReportDefinition
from apps.reports.services import generate_mis_report

User = get_user_model()
admin = User.objects.get(username='admin')
ws, _ = Workspace.objects.get_or_create(
    name="Corporate Analytics Workspace",
    owner=admin,
    defaults={'description': 'Main corporate analytics workspace'}
)
WorkspaceMembership.objects.get_or_create(
    workspace=ws,
    user=admin,
    defaults={'role': WorkspaceRole.ADMIN, 'is_default': True}
)

csv_data = """Invoice_ID,Date,Region,Product_Category,Units_Sold,Unit_Price,Total_Revenue,Payment_Status
INV-1001,2026-01-05,North,Electronics,12,450.00,5400.00,Paid
INV-1002,2026-01-07,South,Furniture,8,320.00,2560.00,Paid
INV-1003,2026-01-10,East,Office Supplies,45,15.50,697.50,Pending
INV-1004,2026-01-14,West,Electronics,5,1200.00,6000.00,Paid
INV-1005,2026-01-18,North,Office Supplies,30,22.00,660.00,Paid
INV-1006,2026-01-22,South,Electronics,15,350.00,5250.00,Paid
INV-1007,2026-01-25,East,Furniture,4,580.00,2320.00,Pending
INV-1008,2026-01-29,West,Office Supplies,60,18.00,1080.00,Paid
INV-1009,2026-02-02,North,Furniture,9,410.00,3690.00,Paid
INV-1010,2026-02-06,South,Office Supplies,50,14.00,700.00,Paid
INV-1011,2026-02-10,East,Electronics,8,890.00,7120.00,Paid
INV-1012,2026-02-15,West,Furniture,6,620.00,3720.00,Paid
"""

f = SimpleUploadedFile('Corporate_Sales_Q1_2026.csv', csv_data.encode('utf-8'), content_type='text/csv')
sf = save_source_file(f, ws, admin)
ds, v1 = ingest_file_to_dataset(sf, dataset_name='Corporate Sales Q1 2026', user=admin)
sm = auto_generate_semantic_model(ds, user=admin)

rep_def, _ = ReportDefinition.objects.get_or_create(
    workspace=ws,
    name='Executive Monthly Sales Performance MIS',
    defaults={
        'report_type': 'sales_mis',
        'dataset': ds,
        'date_column': 'Date',
        'metric_columns': ['Total_Revenue', 'Units_Sold'],
        'dimension_columns': ['Region', 'Product_Category'],
        'created_by': admin
    }
)
run = generate_mis_report(rep_def, user=admin)
print(f"Demo workspace initialized successfully! Dataset rows: {v1.row_count}, Report Run #{run.id}")
