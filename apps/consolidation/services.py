from decimal import Decimal
import pandas as pd
from django.core.exceptions import ValidationError
from apps.datasets.models import Dataset
from apps.datasets.services import load_version_dataframe, save_version_dataframe
from apps.consolidation.models import ConsolidationRun, ReconciliationRun
from apps.core.utils import to_safe_decimal
from apps.audit.services import log_audit

def preview_join_cardinality(left_df, right_df, left_key, right_key):
    """
    Analyzes join cardinality and warns of Cartesian explosions.
    """
    if left_key not in left_df.columns:
        raise ValidationError(f"Primary key '{left_key}' not found in primary dataset.")
    if right_key not in right_df.columns:
        raise ValidationError(f"Secondary key '{right_key}' not found in secondary dataset.")

    left_s = left_df[left_key].dropna().astype(str)
    right_s = right_df[right_key].dropna().astype(str)

    left_unique = left_s.is_unique
    right_unique = right_s.is_unique

    left_keys_set = set(left_s)
    right_keys_set = set(right_s)

    matched_keys = left_keys_set.intersection(right_keys_set)
    unmatched_left = len(left_keys_set - right_keys_set)
    unmatched_right = len(right_keys_set - left_keys_set)

    if left_unique and right_unique:
        cardinality = "1:1"
        warning = "Clean one-to-one relationship. No row multiplication."
    elif left_unique and not right_unique:
        cardinality = "1:N"
        warning = "One-to-many relationship: Primary rows may duplicate to match multiple secondary records."
    elif not left_unique and right_unique:
        cardinality = "N:1"
        warning = "Many-to-one relationship: Multiple primary rows will match single secondary records."
    else:
        cardinality = "N:N"
        warning = "CAUTION: Many-to-many relationship. Potential row explosion or Cartesian explosion."

    # Estimate output rows for left join
    right_counts = right_s.value_counts()
    est_rows = 0
    for val, count in left_s.value_counts().items():
        r_cnt = right_counts.get(val, 0)
        est_rows += int(count) * max(1, int(r_cnt))

    return {
        'cardinality': cardinality,
        'warning': warning,
        'primary_rows': int(len(left_df)),
        'secondary_rows': int(len(right_df)),
        'matched_keys_count': int(len(matched_keys)),
        'unmatched_primary_keys': int(unmatched_left),
        'unmatched_secondary_keys': int(unmatched_right),
        'estimated_output_rows': int(est_rows),
    }

def execute_consolidation(workspace, operation_type, primary_dataset, secondary_dataset, params, user=None):
    """
    Executes Append/Union or Join/Merge between two datasets, creating a new governed Dataset.
    """
    df1 = load_version_dataframe(primary_dataset.active_version)
    df2 = load_version_dataframe(secondary_dataset.active_version)

    new_dataset_name = params.get('name') or f"Consolidated_{primary_dataset.name}_{secondary_dataset.name}"

    if operation_type == 'append':
        # Add source lineage columns
        df1_tagged = df1.copy()
        df2_tagged = df2.copy()
        df1_tagged['__source_file'] = primary_dataset.name
        df2_tagged['__source_file'] = secondary_dataset.name

        combined_df = pd.concat([df1_tagged, df2_tagged], ignore_index=True)
        cardinality_info = {'operation': 'append', 'rows': len(combined_df)}

    elif operation_type == 'join':
        left_key = params.get('primary_key')
        right_key = params.get('secondary_key')
        how = params.get('join_type', 'left')

        cardinality_info = preview_join_cardinality(df1, df2, left_key, right_key)
        
        # Merge
        combined_df = pd.merge(
            df1,
            df2,
            left_on=left_key,
            right_on=right_key,
            how=how,
            suffixes=('', '_secondary')
        )

    # Create new consolidated Dataset
    base_name = new_dataset_name
    counter = 1
    while Dataset.objects.filter(workspace=workspace, name=new_dataset_name).exists():
        new_dataset_name = f"{base_name} ({counter})"
        counter += 1

    new_dataset = Dataset.objects.create(
        workspace=workspace,
        name=new_dataset_name,
        description=f"Consolidated via {operation_type} of '{primary_dataset.name}' and '{secondary_dataset.name}'.",
        created_by=user
    )

    save_version_dataframe(
        dataset=new_dataset,
        df=combined_df,
        change_summary=f"Created via {operation_type} consolidation.",
        user=user
    )

    ConsolidationRun.objects.create(
        workspace=workspace,
        operation_type=operation_type,
        primary_dataset=primary_dataset,
        secondary_dataset=secondary_dataset,
        resulting_dataset=new_dataset,
        join_type=params.get('join_type', 'left') if operation_type == 'join' else '',
        join_keys={'primary_key': params.get('primary_key'), 'secondary_key': params.get('secondary_key')} if operation_type == 'join' else {},
        cardinality_preview=cardinality_info,
        records_produced=len(combined_df),
        created_by=user
    )

    log_audit(
        actor=user,
        event_type="dataset.consolidated",
        description=f"Consolidated datasets '{primary_dataset.name}' and '{secondary_dataset.name}' into '{new_dataset.name}' ({len(combined_df)} rows).",
        workspace=workspace,
        object_type="Dataset",
        object_id=new_dataset.id,
        metadata={"operation": operation_type, "rows": len(combined_df)}
    )

    return new_dataset

def execute_reconciliation(workspace, primary_dataset, secondary_dataset, primary_key, secondary_key, control_total_col1=None, control_total_col2=None, tolerance=0.0, user=None):
    """
    Executes reconciliation between two datasets, verifying record counts, control totals, and variances.
    """
    df1 = load_version_dataframe(primary_dataset.active_version)
    df2 = load_version_dataframe(secondary_dataset.active_version)

    k1 = df1[primary_key].dropna().astype(str)
    k2 = df2[secondary_key].dropna().astype(str)

    set1 = set(k1)
    set2 = set(k2)

    matched = set1.intersection(set2)
    unmatched1 = set1 - set2
    unmatched2 = set2 - set1

    sum1 = Decimal('0.00')
    sum2 = Decimal('0.00')

    if control_total_col1 and control_total_col1 in df1.columns:
        num1 = pd.to_numeric(df1[control_total_col1].astype(str).str.replace(r'[\$,₹€£\s,()]', '', regex=True), errors='coerce').fillna(0)
        sum1 = to_safe_decimal(num1.sum())

    if control_total_col2 and control_total_col2 in df2.columns:
        num2 = pd.to_numeric(df2[control_total_col2].astype(str).str.replace(r'[\$,₹€£\s,()]', '', regex=True), errors='coerce').fillna(0)
        sum2 = to_safe_decimal(num2.sum())

    variance = abs(sum1 - sum2)
    tol = to_safe_decimal(tolerance)
    is_reconciled = (variance <= tol) and (len(unmatched1) == 0 and len(unmatched2) == 0)

    report_summary = {
        'primary_dataset': primary_dataset.name,
        'secondary_dataset': secondary_dataset.name,
        'primary_total_records': len(df1),
        'secondary_total_records': len(df2),
        'matched_records_count': len(matched),
        'unmatched_primary_count': len(unmatched1),
        'unmatched_secondary_count': len(unmatched2),
        'unmatched_primary_sample': list(unmatched1)[:10],
        'unmatched_secondary_sample': list(unmatched2)[:10],
        'sum_primary': float(sum1),
        'sum_secondary': float(sum2),
        'variance': float(variance),
        'tolerance': float(tol),
        'is_reconciled': is_reconciled,
    }

    run = ReconciliationRun.objects.create(
        workspace=workspace,
        name=f"Reconciliation: {primary_dataset.name} vs {secondary_dataset.name}",
        primary_dataset=primary_dataset,
        secondary_dataset=secondary_dataset,
        matching_keys={'primary_key': primary_key, 'secondary_key': secondary_key},
        matched_records_count=len(matched),
        unmatched_primary_count=len(unmatched1),
        unmatched_secondary_count=len(unmatched2),
        control_total_field_1=control_total_col1 or '',
        control_total_field_2=control_total_col2 or '',
        control_total_sum_1=sum1,
        control_total_sum_2=sum2,
        variance=variance,
        tolerance=tol,
        is_reconciled=is_reconciled,
        report_summary=report_summary,
        created_by=user
    )

    log_audit(
        actor=user,
        event_type="dataset.reconciled",
        description=f"Reconciled '{primary_dataset.name}' vs '{secondary_dataset.name}' (Variance: {variance}, Reconciled: {is_reconciled})",
        workspace=workspace,
        object_type="ReconciliationRun",
        object_id=run.id,
        metadata={"variance": float(variance), "is_reconciled": is_reconciled}
    )

    return run
