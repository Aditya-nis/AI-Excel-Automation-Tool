import re
import numpy as np
import pandas as pd
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.datasets.models import Dataset, DatasetVersion
from apps.datasets.services import load_version_dataframe, save_version_dataframe
from apps.cleaning.models import TransformationRun, TransformationStep, CleaningRecipe
from apps.audit.services import log_audit

def apply_single_step(df, step):
    """
    Applies a single cleaning transformation step to DataFrame.
    Returns (modified_df, affected_rows_count, description)
    """
    op_type = step.get('operation_type')
    col = step.get('column_name')
    params = step.get('parameters', {})
    affected_rows = 0
    desc = ""

    df = df.copy()

    if op_type == 'trim_whitespace':
        target_cols = [col] if (col and col in df.columns) else [c for c in df.columns if df[c].dtype == 'object']
        for c in target_cols:
            before = df[c].astype(str)
            after = before.str.strip().str.replace(r'\s{2,}', ' ', regex=True)
            diff_mask = (before != after) & df[c].notna()
            affected_rows += int(diff_mask.sum())
            df[c] = after.replace({'nan': None, 'None': None})
        desc = f"Trimmed whitespace on {', '.join(target_cols)}"

    elif op_type == 'change_case':
        case_type = params.get('case_type', 'title') # title, upper, lower
        if col in df.columns:
            before = df[col].dropna().astype(str)
            if case_type == 'title':
                after = before.str.title()
            elif case_type == 'upper':
                after = before.str.upper()
            elif case_type == 'lower':
                after = before.str.lower()
            else:
                after = before
            diff_mask = before != after
            affected_rows = int(diff_mask.sum())
            df.loc[df[col].notna(), col] = after
            desc = f"Converted case to {case_type} on '{col}'"

    elif op_type == 'normalize_date':
        if col in df.columns:
            date_format = params.get('date_format')
            before_series = df[col].copy()
            if date_format:
                converted = pd.to_datetime(df[col], format=date_format, errors='coerce')
            else:
                converted = pd.to_datetime(df[col], errors='coerce')
            
            diff_mask = converted.notna()
            affected_rows = int(diff_mask.sum())
            df[col] = converted.dt.strftime('%Y-%m-%d')
            desc = f"Normalized dates to ISO format on '{col}'"

    elif op_type == 'convert_type':
        target_type = params.get('target_type', 'numeric')
        if col in df.columns:
            if target_type == 'numeric':
                cleaned = df[col].astype(str).str.replace(r'[\$,₹€£\s,()]', '', regex=True)
                df[col] = pd.to_numeric(cleaned, errors='coerce')
                affected_rows = int(df[col].notna().sum())
            elif target_type == 'integer':
                cleaned = df[col].astype(str).str.replace(r'[\$,₹€£\s,()]', '', regex=True)
                df[col] = pd.to_numeric(cleaned, errors='coerce').round().astype('Int64')
                affected_rows = int(df[col].notna().sum())
            elif target_type == 'text':
                df[col] = df[col].astype(str)
                affected_rows = len(df)
            desc = f"Converted column '{col}' to {target_type}"

    elif op_type == 'remove_duplicates':
        keep = params.get('keep', 'first')
        subset = params.get('subset') or None
        if subset and isinstance(subset, list):
            subset = [c for c in subset if c in df.columns] or None
        initial_count = len(df)
        df = df.drop_duplicates(subset=subset, keep=keep).reset_index(drop=True)
        affected_rows = initial_count - len(df)
        desc = f"Removed {affected_rows} duplicate rows (keep: {keep})"

    elif op_type == 'fill_missing':
        strategy = params.get('strategy', 'literal') # literal, mean, median, mode, ffill, bfill
        val = params.get('fill_value', '')
        if col in df.columns:
            null_mask = df[col].isna() | (df[col].astype(str).str.strip().isin(['', 'nan', 'None']))
            affected_rows = int(null_mask.sum())
            if strategy == 'literal':
                if pd.api.types.is_numeric_dtype(df[col]):
                    try:
                        val = float(val) if (isinstance(val, (int, float, str)) and '.' in str(val)) else int(val)
                    except (ValueError, TypeError):
                        df[col] = df[col].astype(object)
                df.loc[null_mask, col] = val
            elif strategy == 'mean':
                mean_val = pd.to_numeric(df[col], errors='coerce').mean()
                df.loc[null_mask, col] = round(mean_val, 2)
            elif strategy == 'median':
                med_val = pd.to_numeric(df[col], errors='coerce').median()
                df.loc[null_mask, col] = round(med_val, 2)
            elif strategy == 'mode':
                mode_val = df[col].mode().iloc[0] if not df[col].mode().empty else val
                df.loc[null_mask, col] = mode_val
            elif strategy == 'ffill':
                df[col] = df[col].ffill()
            elif strategy == 'bfill':
                df[col] = df[col].bfill()
            desc = f"Filled missing values in '{col}' using {strategy}"

    elif op_type == 'drop_missing':
        how = params.get('how', 'any')
        subset = [col] if (col and col in df.columns) else None
        initial_count = len(df)
        df = df.dropna(how=how, subset=subset).reset_index(drop=True)
        affected_rows = initial_count - len(df)
        desc = f"Dropped {affected_rows} rows with missing values in {col or 'any column'}"

    elif op_type == 'map_categories':
        mapping = params.get('mapping', {})
        if col in df.columns and mapping:
            # Map values
            before = df[col].astype(str)
            df[col] = df[col].replace(mapping)
            after = df[col].astype(str)
            affected_rows = int((before != after).sum())
            desc = f"Mapped {len(mapping)} categories in '{col}'"

    elif op_type == 'filter_rows':
        operator = params.get('operator', 'eq')
        value = params.get('value', '')
        if col in df.columns:
            initial_count = len(df)
            col_series = df[col]
            if operator == 'eq':
                mask = col_series.astype(str) == str(value)
            elif operator == 'neq':
                mask = col_series.astype(str) != str(value)
            elif operator == 'contains':
                mask = col_series.astype(str).str.contains(str(value), case=False, na=False)
            elif operator == 'not_contains':
                mask = ~col_series.astype(str).str.contains(str(value), case=False, na=False)
            elif operator == 'gt':
                mask = pd.to_numeric(col_series, errors='coerce') > float(value)
            elif operator == 'gte':
                mask = pd.to_numeric(col_series, errors='coerce') >= float(value)
            elif operator == 'lt':
                mask = pd.to_numeric(col_series, errors='coerce') < float(value)
            elif operator == 'lte':
                mask = pd.to_numeric(col_series, errors='coerce') <= float(value)
            elif operator == 'is_not_null':
                mask = col_series.notna() & (col_series.astype(str).str.strip() != '')
            else:
                mask = pd.Series([True] * len(df))
            
            df = df[mask].reset_index(drop=True)
            affected_rows = initial_count - len(df)
            desc = f"Filtered rows where {col} {operator} {value} (removed {affected_rows} rows)"

    elif op_type == 'handle_outliers':
        strategy = params.get('strategy', 'cap') # cap or remove
        if col in df.columns:
            num = pd.to_numeric(df[col], errors='coerce')
            mean, std = num.mean(), num.std()
            if std > 0:
                lower = mean - 3 * std
                upper = mean + 3 * std
                outlier_mask = (num < lower) | (num > upper)
                affected_rows = int(outlier_mask.sum())
                if strategy == 'cap':
                    df[col] = num.clip(lower=lower, upper=upper)
                    desc = f"Capped {affected_rows} outliers in '{col}' to 3 std dev bounds"
                elif strategy == 'remove':
                    df = df[~outlier_mask].reset_index(drop=True)
                    desc = f"Removed {affected_rows} outlier rows in '{col}'"

    return df, affected_rows, desc

def preview_transformations(dataset, steps):
    """
    Executes transformations in dry-run mode and returns preview comparison.
    """
    version = dataset.active_version
    df_orig = load_version_dataframe(version)
    df_curr = df_orig.copy()

    step_results = []
    for s in steps:
        df_curr, aff_rows, desc = apply_single_step(df_curr, s)
        step_results.append({
            'step': s,
            'description': desc,
            'affected_rows': aff_rows,
        })

    # Sample comparison (first 10 rows)
    before_preview = df_orig.head(10).to_dict(orient='records')
    after_preview = df_curr.head(10).to_dict(orient='records')

    return {
        'total_rows_before': len(df_orig),
        'total_rows_after': len(df_curr),
        'columns': list(df_curr.columns),
        'steps': step_results,
        'before_sample': before_preview,
        'after_sample': after_preview,
    }

@transaction.atomic
def execute_transformations(dataset, steps, user=None, run_type='manual'):
    """
    Executes transformations, creates immutable derived DatasetVersion, records step lineage.
    """
    source_version = dataset.active_version
    df = load_version_dataframe(source_version)
    rows_before = len(df)

    run = TransformationRun.objects.create(
        dataset=dataset,
        source_version=source_version,
        run_type=run_type,
        status='running',
        steps_count=len(steps),
        rows_before=rows_before,
        created_by=user
    )

    descriptions = []
    for i, s in enumerate(steps, start=1):
        df, aff_rows, desc = apply_single_step(df, s)
        TransformationStep.objects.create(
            run=run,
            step_number=i,
            operation_type=s.get('operation_type', 'trim_whitespace'),
            column_name=s.get('column_name', ''),
            parameters=s.get('parameters', {}),
            affected_rows=aff_rows,
            description=desc
        )
        descriptions.append(desc)

    rows_after = len(df)
    run.rows_after = rows_after
    run.status = 'completed'
    run.save()

    change_summary = "; ".join(descriptions)
    new_version = save_version_dataframe(
        dataset=dataset,
        df=df,
        parent_version=source_version,
        transformation_run=run,
        change_summary=change_summary,
        user=user
    )
    new_version.is_cleaned = True
    new_version.save(update_fields=['is_cleaned'])

    run.target_version = new_version
    run.save(update_fields=['target_version'])

    log_audit(
        actor=user,
        event_type="dataset.transformed",
        description=f"Applied {len(steps)} transformation(s) to '{dataset.name}'. Created v{new_version.version_number}.",
        workspace=dataset.workspace,
        object_type="DatasetVersion",
        object_id=new_version.id,
        metadata={"steps": len(steps), "rows_before": rows_before, "rows_after": rows_after}
    )

    return new_version

def undo_transformation(dataset, user=None):
    """
    Rolls back the active version to its parent version.
    Preserves all versions for complete audit and redo capability.
    """
    active = dataset.active_version
    if not active or not active.parent_version:
        raise ValidationError("No previous version exists to undo to.")
    
    parent = active.parent_version
    dataset.active_version = parent
    dataset.save(update_fields=['active_version', 'updated_at'])

    log_audit(
        actor=user,
        event_type="dataset.undo",
        description=f"Reverted active version of '{dataset.name}' from v{active.version_number} to v{parent.version_number}.",
        workspace=dataset.workspace,
        object_type="Dataset",
        object_id=dataset.id,
        metadata={"reverted_from": active.version_number, "reverted_to": parent.version_number}
    )

    return parent

def restore_version(dataset, version_number, user=None):
    """
    Sets a specific historical version as active.
    """
    target = DatasetVersion.objects.filter(dataset=dataset, version_number=version_number).first()
    if not target:
        raise ValidationError(f"Version {version_number} does not exist for dataset '{dataset.name}'.")
    
    dataset.active_version = target
    dataset.save(update_fields=['active_version', 'updated_at'])

    log_audit(
        actor=user,
        event_type="dataset.restore_version",
        description=f"Restored dataset '{dataset.name}' to active v{version_number}.",
        workspace=dataset.workspace,
        object_type="Dataset",
        object_id=dataset.id,
        metadata={"target_version": version_number}
    )

    return target
