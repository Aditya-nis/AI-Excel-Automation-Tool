import os
import io
import re
import hashlib
from pathlib import Path
from decimal import Decimal
import pandas as pd
import numpy as np
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.datasets.models import SourceFile, Dataset, DatasetVersion, DatasetColumn
from apps.audit.services import log_audit

MAGIC_BYTES = {
    'xlsx': [b'PK\x03\x04'], # Zip file header
    'xls': [b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'], # OLE2 CFB header
}

def validate_uploaded_file(file_obj):
    """Validates file format, magic bytes, size, and integrity."""
    filename = file_obj.name
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    if ext not in ['csv', 'xlsx', 'xls']:
        raise ValidationError("Unsupported file format. Only CSV, XLSX, and XLS files are allowed.")
    
    # Check file size (max 50 MB)
    if file_obj.size > settings.FILE_UPLOAD_MAX_MEMORY_SIZE:
        raise ValidationError(f"File size exceeds maximum allowed limit of {settings.FILE_UPLOAD_MAX_MEMORY_SIZE // (1024*1024)}MB.")
    
    # Verify content signature for Excel
    header = file_obj.read(16)
    file_obj.seek(0)
    if ext in MAGIC_BYTES:
        matches = any(header.startswith(sig) for sig in MAGIC_BYTES[ext])
        if not matches:
            raise ValidationError(f"File content does not match expected {ext.upper()} format signature.")
    
    return ext

def save_source_file(uploaded_file, workspace, user=None):
    """Saves uploaded file and inspects available sheets."""
    ext = validate_uploaded_file(uploaded_file)
    hasher = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        hasher.update(chunk)
    file_hash = hasher.hexdigest()
    uploaded_file.seek(0)

    # Inspect sheet names if Excel
    sheet_names = []
    if ext in ['xlsx', 'xls']:
        try:
            excel_file = pd.ExcelFile(uploaded_file)
            sheet_names = excel_file.sheet_names
            uploaded_file.seek(0)
        except Exception as e:
            raise ValidationError(f"Failed to parse Excel workbook structure: {str(e)}")

    source_file = SourceFile.objects.create(
        workspace=workspace,
        file=uploaded_file,
        filename=uploaded_file.name,
        file_format=ext,
        file_size_bytes=uploaded_file.size,
        sha256_hash=file_hash,
        sheet_names=sheet_names,
        selected_sheet=sheet_names[0] if sheet_names else '',
        uploaded_by=user,
        status='ready'
    )

    log_audit(
        actor=user,
        event_type="file.upload",
        description=f"Uploaded {source_file.filename} ({source_file.file_size_bytes} bytes)",
        workspace=workspace,
        object_type="SourceFile",
        object_id=source_file.id,
        metadata={"filename": source_file.filename, "hash": file_hash, "sheets": sheet_names}
    )

    return source_file

def read_source_file_dataframe(source_file, sheet_name=None):
    """Reads SourceFile into a pandas DataFrame safely with encoding fallback."""
    file_path = source_file.file.path
    ext = source_file.file_format.lower()
    
    if ext == 'csv':
        encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        df = None
        last_error = None
        for enc in encodings:
            try:
                df = pd.read_csv(file_path, encoding=enc, low_memory=False)
                break
            except Exception as e:
                last_error = e
        if df is None:
            raise ValueError(f"Could not read CSV file with standard encodings: {last_error}")
    else:
        target_sheet = sheet_name or source_file.selected_sheet or (source_file.sheet_names[0] if source_file.sheet_names else 0)
        df = pd.read_excel(file_path, sheet_name=target_sheet)

    # Sanitize and align headers
    cleaned_columns = []
    seen = {}
    for i, col in enumerate(df.columns):
        col_str = str(col).strip()
        if not col_str or col_str.startswith('Unnamed:'):
            col_str = f"Column_{i+1}"
        # Deduplicate
        if col_str in seen:
            seen[col_str] += 1
            col_str = f"{col_str}_{seen[col_str]}"
        else:
            seen[col_str] = 1
        cleaned_columns.append(col_str)
    df.columns = cleaned_columns
    return df

def get_storage_path(dataset_id, version_num):
    """Generates storage directory and parquet file path for dataset version."""
    storage_dir = Path(settings.MEDIA_ROOT) / 'datasets' / str(dataset_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    return str(storage_dir / f"v{version_num}.parquet")

def load_version_dataframe(version):
    """Loads DataFrame from immutable Parquet storage."""
    file_path = version.file_path
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Storage file for version {version.version_number} not found at {file_path}")
    return pd.read_parquet(file_path)

def save_version_dataframe(dataset, df, parent_version=None, transformation_run=None, change_summary="", user=None):
    """
    Saves a DataFrame as an immutable new DatasetVersion, performs profiling and quality audit.
    Never overwrites existing files.
    """
    from apps.profiling.services import profile_dataset_version
    from apps.understanding.services import assess_column_semantics
    from apps.data_quality.services import evaluate_data_quality

    next_version_num = (
        DatasetVersion.objects.filter(dataset=dataset).count() + 1
    )
    parquet_path = get_storage_path(dataset.id, next_version_num)
    
    # Ensure types are stored cleanly in Parquet
    # Cast object columns to string representation for consistent storage
    df_to_save = df.copy()
    for col in df_to_save.columns:
        if df_to_save[col].dtype == 'object':
            df_to_save[col] = df_to_save[col].astype(str).replace({'nan': None, 'None': None, '<NA>': None})
            
    df_to_save.to_parquet(parquet_path, index=False, engine='pyarrow')

    version = DatasetVersion.objects.create(
        dataset=dataset,
        version_number=next_version_num,
        parent_version=parent_version,
        transformation_run=transformation_run,
        file_path=parquet_path,
        row_count=len(df),
        column_count=len(df.columns),
        change_summary=change_summary,
        created_by=user
    )

    dataset.active_version = version
    dataset.save(update_fields=['active_version', 'updated_at'])

    # Profile & Evaluate Data Quality
    profile_dataset_version(version, df)
    assess_column_semantics(version, df)
    quality_report = evaluate_data_quality(version, df)
    version.quality_score = quality_report.overall_score
    version.save(update_fields=['quality_score'])

    log_audit(
        actor=user,
        event_type="dataset.version_created",
        description=f"Created version {version.version_number} for dataset '{dataset.name}' ({len(df)} rows, {len(df.columns)} columns)",
        workspace=dataset.workspace,
        object_type="DatasetVersion",
        object_id=version.id,
        metadata={"rows": len(df), "columns": len(df.columns), "quality_score": version.quality_score}
    )

    return version

def ingest_file_to_dataset(source_file, dataset_name=None, sheet_name=None, user=None):
    """
    Ingests SourceFile into a new Dataset with immutable Version 1.
    """
    df = read_source_file_dataframe(source_file, sheet_name=sheet_name)
    name = dataset_name or Path(source_file.filename).stem
    
    # Ensure unique name in workspace
    base_name = name
    counter = 1
    while Dataset.objects.filter(workspace=source_file.workspace, name=name).exists():
        name = f"{base_name} ({counter})"
        counter += 1

    dataset = Dataset.objects.create(
        workspace=source_file.workspace,
        name=name,
        description=f"Imported from {source_file.filename}" + (f" (Sheet: {sheet_name})" if sheet_name else ""),
        source_file=source_file,
        created_by=user
    )

    version = save_version_dataframe(
        dataset=dataset,
        df=df,
        parent_version=None,
        change_summary="Initial ingestion from source file",
        user=user
    )

    return dataset, version
