import re
import time
from decimal import Decimal
import pandas as pd
import numpy as np
from apps.ask_data.models import ChatSession, QueryRun
from apps.datasets.services import load_version_dataframe
from apps.core.utils import to_safe_decimal, SafeJSONEncoder
from apps.audit.services import log_audit

def compile_and_execute_query(dataset, user_query, semantic_model=None):
    """
    Safely compiles natural language query into deterministic analytical plan and executes it.
    Zero prompt injection risk: only uses allowlisted column schemas and deterministic DataFrame operations.
    """
    start_time = time.time()
    df = load_version_dataframe(dataset.active_version)
    q_lower = user_query.lower()
    caveats = []

    # Columns inventory
    cols = list(df.columns)
    col_map = {c.lower(): c for c in cols}

    # Find candidate measure column
    numeric_cols = [c for c in cols if pd.to_numeric(df[c].astype(str).str.replace(r'[\$,₹€£\s,()]', '', regex=True), errors='coerce').notna().sum() / max(1, len(df)) >= 0.5]
    
    selected_measure = None
    for nc in numeric_cols:
        if nc.lower() in q_lower or any(part in q_lower for part in nc.lower().split('_')):
            selected_measure = nc
            break
    if not selected_measure and numeric_cols:
        # Default to first monetary or numeric measure
        for nc in numeric_cols:
            if any(term in nc.lower() for term in ['amount', 'sales', 'revenue', 'price', 'total', 'profit', 'val', 'qty', 'count']):
                selected_measure = nc
                break
        if not selected_measure:
            selected_measure = numeric_cols[0]

    # Find candidate dimension column
    dim_cols = [c for c in cols if c != selected_measure and df[c].nunique() < len(df) * 0.9]
    selected_dimension = None
    for dc in dim_cols:
        if dc.lower() in q_lower or any(part in q_lower for part in dc.lower().split('_')):
            selected_dimension = dc
            break

    # Determine aggregation function
    agg_func = 'sum'
    if any(term in q_lower for term in ['average', 'avg', 'mean']):
        agg_func = 'mean'
    elif any(term in q_lower for term in ['count', 'number of', 'how many']):
        agg_func = 'count'
    elif any(term in q_lower for term in ['maximum', 'max', 'highest', 'top', 'peak']):
        agg_func = 'max' if not selected_dimension else 'sum' # If dimension present, usually sum grouped then sorted
    elif any(term in q_lower for term in ['minimum', 'min', 'lowest']):
        agg_func = 'min'

    # Filter parsing
    filtered_df = df.copy()
    filter_applied_desc = []
    for dc in dim_cols:
        unique_vals = [str(v) for v in df[dc].dropna().unique() if len(str(v)) > 1]
        for uval in unique_vals:
            if f" {uval.lower()} " in f" {q_lower} " or f"'{uval.lower()}'" in q_lower or f'"{uval.lower()}"' in q_lower:
                filtered_df = filtered_df[filtered_df[dc].astype(str).str.lower() == uval.lower()]
                filter_applied_desc.append(f"{dc} = '{uval}'")
                break

    if filter_applied_desc:
        caveats.append(f"Applied filters: {', '.join(filter_applied_desc)}")

    # Clean measure values for calculation
    if selected_measure:
        filtered_df['__calc_meas'] = pd.to_numeric(
            filtered_df[selected_measure].astype(str).str.replace(r'[\$,₹€£\s,()]', '', regex=True),
            errors='coerce'
        )
    else:
        filtered_df['__calc_meas'] = 1
        selected_measure = "Record_Count"

    # Top N limit check
    top_limit = 10
    top_match = re.search(r'\btop\s+(\d+)\b', q_lower)
    if top_match:
        top_limit = int(top_match.group(1))

    # Perform calculation
    chart_type = 'table'
    if selected_dimension and selected_dimension in filtered_df.columns:
        # Grouped aggregate
        grouped = filtered_df.groupby(selected_dimension)['__calc_meas'].agg(agg_func).reset_index()
        
        # Sort descending by default for business intelligence
        grouped = grouped.sort_values(by='__calc_meas', ascending=('lowest' in q_lower or 'bottom' in q_lower)).head(top_limit)
        
        labels = [str(x) for x in grouped[selected_dimension]]
        values = [round(float(y), 2) if pd.notna(y) else 0.0 for y in grouped['__calc_meas']]
        
        result_table = {
            'headers': [selected_dimension, f"{agg_func.upper()} of {selected_measure}"],
            'rows': [[labels[i], values[i]] for i in range(len(labels))]
        }
        
        # Select chart type
        if any(term in selected_dimension.lower() for term in ['date', 'month', 'year', 'day']):
            chart_type = 'line'
        elif len(labels) <= 6 and agg_func == 'sum':
            chart_type = 'pie'
        else:
            chart_type = 'bar'

        summary_text = f"{agg_func.upper()} of {selected_measure} analyzed across {len(labels)} categories of '{selected_dimension}'."
    else:
        # Single KPI aggregate
        val = filtered_df['__calc_meas'].agg(agg_func)
        safe_val = round(float(val), 2) if pd.notna(val) else 0.0
        
        chart_type = 'kpi'
        result_table = {
            'headers': [f"{agg_func.upper()} of {selected_measure}"],
            'rows': [[safe_val]]
        }
        labels = [selected_measure]
        values = [safe_val]
        summary_text = f"Total {agg_func.upper()} for '{selected_measure}' is {safe_val:,.2f} across {len(filtered_df):,} records."

    exec_time = round((time.time() - start_time) * 1000, 2)

    result_data = {
        'summary': summary_text,
        'table': result_table,
        'chart': {
            'type': chart_type,
            'labels': labels,
            'values': values,
            'measure': selected_measure,
        },
        'records_analyzed': len(filtered_df),
        'execution_ms': exec_time,
    }

    return {
        'parsed_intent': {
            'measure': selected_measure,
            'dimension': selected_dimension,
            'aggregation': agg_func,
            'limit': top_limit,
            'filters': filter_applied_desc
        },
        'generated_query_plan': {
            'engine': 'Deterministic Pandas/In-Memory Compiler',
            'operation': 'groupby' if selected_dimension else 'aggregate',
            'measure_column': selected_measure,
            'dimension_column': selected_dimension,
            'agg_func': agg_func,
        },
        'result_data': result_data,
        'caveats': caveats,
        'confidence_score': 0.94 if selected_measure else 0.70,
        'execution_time_ms': exec_time,
        'recommended_chart': chart_type,
    }

def handle_user_query(session, user_query, user=None):
    """Handles conversational Ask Your Data request and stores QueryRun."""
    plan = compile_and_execute_query(
        dataset=session.dataset,
        user_query=user_query,
        semantic_model=session.semantic_model
    )

    query_run = QueryRun.objects.create(
        session=session,
        user_query=user_query,
        parsed_intent=plan['parsed_intent'],
        generated_query_plan=plan['generated_query_plan'],
        result_data=plan['result_data'],
        caveats=plan['caveats'],
        confidence_score=plan['confidence_score'],
        execution_time_ms=plan['execution_time_ms'],
        recommended_chart=plan['recommended_chart']
    )

    log_audit(
        actor=user,
        event_type="ask_data.query",
        description=f"Asked: '{user_query[:60]}' on dataset '{session.dataset.name}'",
        workspace=session.workspace,
        object_type="QueryRun",
        object_id=query_run.id,
        metadata={"execution_ms": plan['execution_time_ms'], "chart": plan['recommended_chart']}
    )

    return query_run
