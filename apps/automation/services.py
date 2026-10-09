import time
from django.utils import timezone
from apps.automation.models import WorkflowSchedule, JobRun
from apps.cleaning.services import execute_transformations, preview_transformations
from apps.reports.services import generate_mis_report
from apps.datasets.services import load_version_dataframe
from apps.audit.services import log_audit

def detect_schema_drift(target_schema, current_columns):
    """
    Checks whether incoming dataset schema has drifted from expected schema.
    Returns (has_drift, drift_details)
    """
    if not target_schema:
        return False, {}

    expected_cols = set(target_schema.get('columns', []))
    current_cols = set(current_columns)

    missing_cols = list(expected_cols - current_cols)
    new_cols = list(current_cols - expected_cols)

    has_drift = len(missing_cols) > 0
    drift_details = {
        'missing_required_columns': missing_cols,
        'new_columns_introduced': new_cols,
        'expected_columns_count': len(expected_cols),
        'actual_columns_count': len(current_cols),
    }

    return has_drift, drift_details

def run_workflow_job(workflow, trigger_type='manual', user=None, source_file=None):
    """
    Executes a scheduled or manual workflow run with schema-drift protection.
    """
    start_time = time.time()
    job = JobRun.objects.create(
        workflow=workflow,
        trigger_type=trigger_type,
        status='running',
        source_file=source_file,
        started_at=timezone.now()
    )

    dataset = workflow.dataset
    version = dataset.active_version
    recipe = workflow.cleaning_recipe
    df = load_version_dataframe(version)

    # 1. Schema Drift Check
    has_drift, drift_details = detect_schema_drift(recipe.target_schema, list(df.columns))
    
    if has_drift and workflow.stop_on_drift:
        job.status = 'drift_detected'
        job.schema_drift_detected = True
        job.drift_details = drift_details
        job.execution_logs = f"HALTED: Schema drift detected! Missing required columns: {drift_details['missing_required_columns']}"
        job.completed_at = timezone.now()
        job.duration_seconds = round(time.time() - start_time, 2)
        job.save()

        log_audit(
            actor=user,
            event_type="automation.drift_halted",
            description=f"Workflow '{workflow.name}' halted due to schema drift.",
            workspace=workflow.workspace,
            object_type="JobRun",
            object_id=job.id,
            metadata=drift_details
        )
        return job

    # 2. Execution (Dry-Run or Full Execution)
    try:
        steps = recipe.steps_config
        if workflow.dry_run_mode:
            preview = preview_transformations(dataset, steps)
            job.status = 'completed'
            job.execution_logs = f"Dry-run executed successfully. Steps simulated: {len(steps)}. Rows before: {preview['total_rows_before']}, rows after: {preview['total_rows_after']}."
        else:
            new_version = execute_transformations(
                dataset=dataset,
                steps=steps,
                user=user,
                run_type=f"workflow_{trigger_type}"
            )
            job.output_version = new_version
            job.status = 'completed'
            job.execution_logs = f"Workflow completed successfully. Created v{new_version.version_number}."

            # 3. Generate Report if configured
            if workflow.report_definition:
                rep_run = generate_mis_report(workflow.report_definition, user=user)
                job.report_run = rep_run

        workflow.last_run_at = timezone.now()
        workflow.save(update_fields=['last_run_at'])

    except Exception as e:
        job.status = 'failed'
        job.execution_logs = f"Execution failed with error: {str(e)}"

    job.completed_at = timezone.now()
    job.duration_seconds = round(time.time() - start_time, 2)
    job.save()

    log_audit(
        actor=user,
        event_type="automation.job_completed",
        description=f"Workflow '{workflow.name}' job #{job.id} finished with status '{job.status}'.",
        workspace=workflow.workspace,
        object_type="JobRun",
        object_id=job.id,
        metadata={"status": job.status, "duration": job.duration_seconds}
    )

    return job
