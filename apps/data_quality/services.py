import re
import numpy as np
import pandas as pd
from apps.data_quality.models import DataQualityIssue, DataQualityReport
from apps.datasets.models import DatasetColumn

def evaluate_data_quality(version, df):
    """
    Evaluates dataset quality issues, calculates component metrics, and creates DataQualityReport.
    Documented Formula:
      Completeness = max(0, 100 - (missing_cells / total_cells * 100))
      Uniqueness   = max(0, 100 - (duplicate_rows / total_rows * 100))
      Validity     = max(0, 100 - (invalid_values / total_cells * 100))
      Consistency  = max(0, 100 - (inconsistent_formatting_issues / total_rows * 100))
      OverallScore = 0.35 * Completeness + 0.30 * Uniqueness + 0.20 * Validity + 0.15 * Consistency
    """
    total_rows = len(df)
    total_cols = len(df.columns)
    total_cells = total_rows * total_cols if total_rows > 0 and total_cols > 0 else 1

    # Clear existing issues for this version
    DataQualityIssue.objects.filter(version=version).delete()

    missing_cells = 0
    duplicate_rows_count = 0
    invalid_values_count = 0
    inconsistency_count = 0

    # 1. Missing Values Detection
    for col in df.columns:
        series = df[col]
        # Nulls, empty strings, strings that are just spaces
        null_mask = series.isna() | (series.astype(str).str.strip().isin(['', 'nan', 'none', 'null', '<na>']))
        col_null_count = int(null_mask.sum())
        if col_null_count > 0:
            missing_cells += col_null_count
            sample_indices = df[null_mask].index.tolist()[:10]
            DataQualityIssue.objects.create(
                version=version,
                column_name=col,
                issue_type='missing_values',
                severity='critical' if (col_null_count / total_rows > 0.25) else 'warning',
                affected_row_count=col_null_count,
                evidence_summary=f"Found {col_null_count} empty or blank cells ({round(col_null_count/total_rows*100, 1)}% of rows).",
                sample_row_indices=sample_indices,
                suggested_action='fill_missing',
                suggested_params={'column': col, 'strategy': 'literal', 'fill_value': 'N/A'}
            )

    # 2. Duplicate Rows Detection
    if total_rows > 1:
        dup_mask = df.duplicated(keep=False)
        duplicate_rows_count = int(dup_mask.sum())
        if duplicate_rows_count > 0:
            dup_indices = df[dup_mask].index.tolist()[:15]
            DataQualityIssue.objects.create(
                version=version,
                column_name='',
                issue_type='duplicate_rows',
                severity='critical' if duplicate_rows_count > 5 else 'warning',
                affected_row_count=duplicate_rows_count,
                evidence_summary=f"Found {duplicate_rows_count} rows that share identical values across all columns.",
                sample_row_indices=dup_indices,
                suggested_action='remove_duplicates',
                suggested_params={'keep': 'first', 'subset': None}
            )

    # 3. Text Inconsistencies (casing & whitespace)
    for col in df.columns:
        if df[col].dtype == 'object':
            str_series = df[col].dropna().astype(str)
            whitespace_mask = str_series != str_series.str.strip()
            double_space_mask = str_series.str.contains(r'\s{2,}', regex=True)
            flawed_mask = whitespace_mask | double_space_mask
            flawed_count = int(flawed_mask.sum())
            if flawed_count > 0:
                inconsistency_count += flawed_count
                DataQualityIssue.objects.create(
                    version=version,
                    column_name=col,
                    issue_type='inconsistent_casing',
                    severity='info',
                    affected_row_count=flawed_count,
                    evidence_summary=f"{flawed_count} values contain leading/trailing whitespace or multiple internal spaces.",
                    sample_row_indices=df[flawed_mask].index.tolist()[:10],
                    suggested_action='trim_whitespace',
                    suggested_params={'column': col}
                )

            # Category casing variation check (e.g. 'Pending' vs 'pending')
            lower_to_originals = {}
            for val in str_series.unique():
                val_clean = val.strip()
                if not val_clean:
                    continue
                k = val_clean.lower()
                lower_to_originals.setdefault(k, set()).add(val_clean)
            
            casing_conflicts = [vals for vals in lower_to_originals.values() if len(vals) > 1]
            if casing_conflicts:
                conflict_examples = [list(c) for c in casing_conflicts[:3]]
                DataQualityIssue.objects.create(
                    version=version,
                    column_name=col,
                    issue_type='category_variation',
                    severity='warning',
                    affected_row_count=len(casing_conflicts),
                    evidence_summary=f"Column has inconsistent casing variations across the same entities: {conflict_examples}",
                    sample_row_indices=[],
                    suggested_action='change_case',
                    suggested_params={'column': col, 'case_type': 'title'}
                )

    # 4. Outliers in numeric columns
    for col in df.columns:
        num_clean = pd.to_numeric(
            df[col].astype(str).str.replace(r'[\$,₹€£\s,()]', '', regex=True),
            errors='coerce'
        ).dropna()
        if len(num_clean) >= 10:
            mean = num_clean.mean()
            std = num_clean.std()
            if std > 0:
                z_scores = np.abs((num_clean - mean) / std)
                outliers = num_clean[z_scores > 3.0]
                if len(outliers) > 0:
                    DataQualityIssue.objects.create(
                        version=version,
                        column_name=col,
                        issue_type='outlier',
                        severity='warning',
                        affected_row_count=len(outliers),
                        evidence_summary=f"{len(outliers)} values deviate by more than 3 standard deviations from average (mean: {round(mean, 2)}, std: {round(std, 2)}).",
                        sample_row_indices=outliers.index.tolist()[:10],
                        suggested_action='handle_outliers',
                        suggested_params={'column': col, 'strategy': 'cap'}
                    )

    # Compute Component Scores
    completeness = max(0.0, min(100.0, 100.0 - (missing_cells / total_cells * 100.0)))
    uniqueness = max(0.0, min(100.0, 100.0 - (duplicate_rows_count / total_rows * 100.0))) if total_rows > 0 else 100.0
    validity = max(0.0, min(100.0, 100.0 - (invalid_values_count / total_cells * 100.0)))
    consistency = max(0.0, min(100.0, 100.0 - (inconsistency_count / total_rows * 100.0))) if total_rows > 0 else 100.0

    overall_score = round(
        0.35 * completeness + 0.30 * uniqueness + 0.20 * validity + 0.15 * consistency,
        1
    )

    total_issues = DataQualityIssue.objects.filter(version=version).count()

    report, _ = DataQualityReport.objects.update_or_create(
        version=version,
        defaults={
            'overall_score': overall_score,
            'completeness_score': round(completeness, 1),
            'uniqueness_score': round(uniqueness, 1),
            'validity_score': round(validity, 1),
            'consistency_score': round(consistency, 1),
            'scoring_formula': "Overall = (0.35 * Completeness) + (0.30 * Uniqueness) + (0.20 * Validity) + (0.15 * Consistency)",
            'total_issues_count': total_issues,
        }
    )

    return report
