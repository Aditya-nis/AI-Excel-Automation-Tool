import numpy as np
import pandas as pd
from apps.anomalies.models import AnomalyEvent, MetricForecast
from apps.datasets.services import load_version_dataframe
from apps.audit.services import log_audit

def detect_anomalies_for_dataset(dataset, user=None):
    """
    Empirical statistical anomaly detection on active dataset version.
    Identifies metric spikes, 3-sigma deviations, and volume drop-offs without inventing facts.
    """
    version = dataset.active_version
    if not version:
        return []

    df = load_version_dataframe(version)
    anomalies_created = []

    # Clear prior open anomalies for this dataset to avoid duplicate alert fatigue
    AnomalyEvent.objects.filter(dataset=dataset, review_status='open').delete()

    # Find numeric measures
    numeric_cols = [c.name for c in version.columns.all() if c.data_type in ['integer', 'decimal'] or c.inferred_role in ['currency', 'measure', 'quantity']]

    for col in numeric_cols:
        series = pd.to_numeric(df[col].astype(str).str.replace(r'[\$,₹€£\s,()]', '', regex=True), errors='coerce').dropna()
        if len(series) < 5:
            continue

        mean = float(series.mean())
        std = float(series.std()) if len(series) > 1 else 0.0
        
        if std > 0:
            z_scores = np.abs((series - mean) / std)
            outlier_mask = z_scores >= 2.5
            outliers = series[outlier_mask]

            for idx, val in outliers.items():
                z_val = float(z_scores[idx])
                dev_pct = round(((val - mean) / abs(mean)) * 100, 1) if mean != 0 else 100.0
                sev = 'critical' if z_val >= 3.0 else 'warning'

                ev = AnomalyEvent.objects.create(
                    workspace=dataset.workspace,
                    dataset=dataset,
                    metric_name=col,
                    observed_value=round(float(val), 2),
                    baseline_value=round(mean, 2),
                    deviation_percent=dev_pct,
                    z_score=round(z_val, 2),
                    severity=sev,
                    detection_method='z_score_3sigma',
                    evidence=f"Value {val} deviates {dev_pct}% from mean baseline ({round(mean, 2)}) with Z-score {round(z_val, 2)}.",
                    period_label=f"Row #{idx + 1}"
                )
                anomalies_created.append(ev)

    log_audit(
        actor=user,
        event_type="anomaly.scan",
        description=f"Anomaly scan on '{dataset.name}' identified {len(anomalies_created)} statistical deviations.",
        workspace=dataset.workspace,
        object_type="Dataset",
        object_id=dataset.id,
        metadata={"count": len(anomalies_created)}
    )

    return anomalies_created

def generate_metric_forecast(dataset, metric_name, date_col, horizon=3, user=None):
    """
    Grounded statistical forecasting using linear trend regression with prediction uncertainty bounds.
    Requires at least 3 historical periods. Labeled strictly as estimate.
    """
    version = dataset.active_version
    df = load_version_dataframe(version)

    if metric_name not in df.columns or date_col not in df.columns:
        raise ValueError(f"Required columns '{metric_name}' or '{date_col}' not found in dataset.")

    df_calc = df[[date_col, metric_name]].dropna().copy()
    df_calc['__num'] = pd.to_numeric(df_calc[metric_name].astype(str).str.replace(r'[\$,₹€£\s,()]', '', regex=True), errors='coerce')
    df_calc = df_calc.dropna().sort_values(by=date_col)

    if len(df_calc) < 3:
        raise ValueError("Insufficient historical periods (minimum 3 required) to compute an empirical forecast.")

    y = df_calc['__num'].values
    x = np.arange(len(y))

    # Linear regression fit: y = slope * x + intercept
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    residuals = y - fitted
    mae = float(np.mean(np.abs(residuals)))

    forecast_results = []
    last_period_idx = len(y)

    for step in range(1, horizon + 1):
        future_x = last_period_idx + step - 1
        predicted_val = round(float(slope * future_x + intercept), 2)
        uncertainty = round(mae * 1.5, 2)

        forecast_results.append({
            'period': f"Forecast +{step}",
            'estimate': predicted_val,
            'lower_bound': round(max(0, predicted_val - uncertainty), 2),
            'upper_bound': round(predicted_val + uncertainty, 2),
        })

    model = MetricForecast.objects.create(
        dataset=dataset,
        metric_name=metric_name,
        date_column=date_col,
        method="Linear Trend with Empirical Residual Intervals",
        historical_points=len(y),
        horizon_periods=horizon,
        forecast_results=forecast_results,
        mae_error=round(mae, 2),
        assumptions=f"Fitted slope={round(float(slope), 2)}, intercept={round(float(intercept), 2)} over {len(y)} historical datapoints."
    )

    log_audit(
        actor=user,
        event_type="forecast.generated",
        description=f"Generated {horizon}-step empirical forecast for '{metric_name}' on '{dataset.name}'.",
        workspace=dataset.workspace,
        object_type="MetricForecast",
        object_id=model.id,
        metadata={"mae": round(mae, 2), "horizon": horizon}
    )

    return model
