import re
import numpy as np
import pandas as pd
from apps.datasets.models import DatasetColumn, ColumnProfile
from apps.core.utils import to_safe_decimal

def infer_column_type(series, non_null_count, unique_count):
    """Accurately infers column data type using data inspection."""
    if non_null_count == 0:
        return 'text'
    
    # Check boolean
    bool_vals = {'true', 'false', '1', '0', 'yes', 'no', 'y', 'n'}
    str_vals = series.dropna().astype(str).str.strip().str.lower()
    if set(str_vals.unique()).issubset(bool_vals) and unique_count <= 2:
        return 'boolean'
    
    # Check numeric
    numeric_series = pd.to_numeric(
        series.astype(str).str.replace(r'[\$,₹€£\s,()]', '', regex=True),
        errors='coerce'
    )
    valid_numeric_count = numeric_series.notna().sum()
    if valid_numeric_count / non_null_count >= 0.85:
        # Check integer vs decimal
        is_int = (numeric_series.dropna() % 1 == 0).all()
        return 'integer' if is_int else 'decimal'

    # Check date
    # Attempt parsing dates with sample
    sample = series.dropna().head(100).astype(str)
    date_matches = 0
    date_patterns = [
        r'^\d{4}-\d{2}-\d{2}',
        r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',
        r'^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',
    ]
    for val in sample:
        val_clean = val.strip().lower()
        if any(re.search(pat, val_clean) for pat in date_patterns):
            try:
                pd.to_datetime(val_clean, errors='raise')
                date_matches += 1
            except Exception:
                pass
    if date_matches / len(sample) >= 0.75:
        return 'date'

    # Check category vs text
    if unique_count <= 50 and unique_count < non_null_count * 0.4:
        return 'category'

    return 'text'

def profile_dataset_version(version, df):
    """
    Computes statistical profiles for all columns in a DatasetVersion.
    Creates DatasetColumn and ColumnProfile database records.
    """
    total_rows = len(df)
    columns_to_create = []
    profiles_to_create = []

    # Clean existing columns if re-profiling
    DatasetColumn.objects.filter(version=version).delete()

    for idx, col_name in enumerate(df.columns):
        series = df[col_name]
        non_null_series = series.dropna()
        null_count = total_rows - len(non_null_series)
        null_pct = round((null_count / total_rows * 100) if total_rows > 0 else 0.0, 2)
        distinct_count = non_null_series.nunique()
        unique_pct = round((distinct_count / total_rows * 100) if total_rows > 0 else 0.0, 2)
        
        inferred_type = infer_column_type(series, len(non_null_series), distinct_count)
        is_pk = (null_count == 0 and distinct_count == total_rows and total_rows > 0)
        
        col_obj = DatasetColumn(
            version=version,
            name=col_name,
            original_name=col_name,
            display_label=col_name.replace('_', ' ').title(),
            ordinal_position=idx,
            data_type=inferred_type,
            is_primary_key=is_pk
        )
        col_obj.save()

        # Compute summary statistics
        min_val, max_val = None, None
        mean_val, std_val, median_val, q25, q75 = None, None, None, None, None
        outlier_count = 0

        if inferred_type in ['integer', 'decimal']:
            num_clean = pd.to_numeric(
                series.astype(str).str.replace(r'[\$,₹€£\s,()]', '', regex=True),
                errors='coerce'
            ).dropna()
            
            if len(num_clean) > 0:
                min_val = str(round(float(num_clean.min()), 2))
                max_val = str(round(float(num_clean.max()), 2))
                mean_val = round(float(num_clean.mean()), 2)
                std_val = round(float(num_clean.std()), 2) if len(num_clean) > 1 else 0.0
                median_val = round(float(num_clean.median()), 2)
                q25 = round(float(num_clean.quantile(0.25)), 2)
                q75 = round(float(num_clean.quantile(0.75)), 2)
                
                # Outlier detection via IQR
                iqr = q75 - q25
                if iqr > 0:
                    lower_bound = q25 - 1.5 * iqr
                    upper_bound = q75 + 1.5 * iqr
                    outlier_count = int(((num_clean < lower_bound) | (num_clean > upper_bound)).sum())
        elif len(non_null_series) > 0:
            min_val = str(non_null_series.min())[:100]
            max_val = str(non_null_series.max())[:100]

        # Top categories
        top_cats = []
        if len(non_null_series) > 0:
            val_counts = non_null_series.astype(str).value_counts().head(10)
            for val, cnt in val_counts.items():
                top_cats.append({
                    "value": str(val)[:50],
                    "count": int(cnt),
                    "percentage": round(float(cnt / total_rows * 100), 1)
                })

        # Sample values
        sample_vals = [str(v) for v in non_null_series.unique()[:5]]

        ColumnProfile.objects.create(
            column=col_obj,
            null_count=null_count,
            null_percentage=null_pct,
            distinct_count=distinct_count,
            unique_percentage=unique_pct,
            min_value=min_val,
            max_value=max_val,
            mean_value=mean_val,
            std_value=std_val,
            median_value=median_val,
            q25=q25,
            q75=q75,
            outlier_count=outlier_count,
            sample_values=sample_vals,
            top_categories=top_cats
        )
