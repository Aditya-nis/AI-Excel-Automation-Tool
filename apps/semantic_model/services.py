import re
from apps.semantic_model.models import SemanticModel, SemanticDimension, SemanticMeasure
from apps.datasets.models import DatasetColumn
from apps.core.utils import to_safe_decimal, safe_divide

def auto_generate_semantic_model(dataset, user=None):
    """
    Auto-discovers dimensions, measures, and KPIs from DatasetColumn profiles.
    """
    version = dataset.active_version
    if not version:
        return None

    model, _ = SemanticModel.objects.get_or_create(
        workspace=dataset.workspace,
        name=f"Governed Model: {dataset.name}",
        defaults={
            'primary_dataset': dataset,
            'description': f"Automated semantic model derived from {dataset.name} v{version.version_number}.",
            'is_default': True,
            'created_by': user
        }
    )

    columns = DatasetColumn.objects.filter(version=version)
    
    for col in columns:
        role = col.inferred_role
        col_name = col.name
        label = col.display_label or col_name.replace('_', ' ').title()

        if role in ['dimension', 'status', 'category', 'text'] or col.data_type == 'category':
            SemanticDimension.objects.get_or_create(
                semantic_model=model,
                name=col_name,
                defaults={
                    'column_name': col_name,
                    'display_label': label,
                    'dimension_type': 'categorical'
                }
            )
        elif role == 'date' or col.data_type == 'date':
            SemanticDimension.objects.get_or_create(
                semantic_model=model,
                name=col_name,
                defaults={
                    'column_name': col_name,
                    'display_label': label,
                    'dimension_type': 'time'
                }
            )
        elif role in ['currency', 'measure', 'quantity', 'percentage'] or col.data_type in ['decimal', 'integer']:
            fmt = 'currency' if role == 'currency' else ('percentage' if role == 'percentage' else ('integer' if role == 'quantity' else 'number'))
            is_kpi = role in ['currency', 'measure'] or any(k in col_name.lower() for k in ['total', 'revenue', 'sales', 'profit'])
            
            SemanticMeasure.objects.get_or_create(
                semantic_model=model,
                name=col_name,
                defaults={
                    'display_label': f"Total {label}",
                    'column_name': col_name,
                    'aggregation_type': 'sum',
                    'format_type': fmt,
                    'currency_symbol': '₹' if fmt == 'currency' else '',
                    'is_kpi': is_kpi
                }
            )

    return model
