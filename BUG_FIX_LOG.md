# Bug Fix & Remediation Log

This document records all confirmed issues discovered, diagnosed, and resolved during the comprehensive audit of the AI Power BI + Data Cleaning + MIS Report Engine.

---

### Issue FIX-001: Accounting Negative Numbers Converted to Positive Amounts
* **Severity**: P1 — High (Financial Data Integrity)
* **Affected Files**:
  - `apps/cleaning/services.py`
  - `apps/dashboards/views.py`
  - `apps/reports/services.py`
  - `apps/ask_data/services.py`
  - `apps/anomalies/services.py`
* **Root Cause**: Regular expressions used `str.replace(r'[\$,₹€£\s,()]', '', regex=True)` before `pd.to_numeric()`. In standard financial/ERP balance sheets, parenthesized amounts like `(500.00)` or `($1,250.00)` denote negative numbers. Stripping parentheses converted them to `+500.00` and `+1250.00`, corrupting totals and KPI sums.
* **Fix Implemented**: Replaced with intelligent numeric cleaners (`clean_numeric_series` and `_clean_val`) that recognize:
  1. Parentheses `(x)` $\to$ `-x`
  2. Leading minus `-x` $\to$ `-x`
  3. Trailing ERP minus `x-` $\to$ `-x`
  4. Currency symbols and thousands commas stripped safely.
* **Regression Test Added**: `tests.test_financial_accuracy.FinancialAccuracyTests.test_clean_numeric_series_accounting_formats` and `test_cleaning_engine_convert_type_negative_preservation`.
* **Verification Result**: Verified. `(500.00)` converts to `-500.00`, and `sum` across sample records equals `2,750.75` instead of inflated positive sums.

---

### Issue FIX-002: Potential Script Injection (XSS) via Inline Chart Payloads
* **Severity**: P2 — Medium (Application Security)
* **Affected Files**:
  - `templates/dashboards/home.html`
  - `templates/dashboards/analytics.html`
  - `templates/dashboards/period_report.html`
* **Root Cause**: Chart labels derived from user-uploaded column headers or category values were injected directly into JavaScript tags using `{{ chart_data.labels|safe }}`. If an uploaded column name contained `</script><script>...`, it could break out of the script tag.
* **Fix Implemented**: Replaced inline `|safe` injections with Django's built-in `json_script` tag (`{{ chart_data|json_script:"main-chart-data" }}`). JavaScript reads the payload safely using `JSON.parse(document.getElementById(...).textContent)`.
* **Regression Test Added**: `tests.test_security_audit.SecurityAuditTests.test_safe_json_encoder_xss_prevention`.
* **Verification Result**: Verified. All HTML entities and script tags are serialized safely to RFC 8259-compliant JSON.

---

### Issue FIX-003: Non-RFC 8259 Compliant `NaN` Output in SafeJSONEncoder
* **Severity**: P2 — Medium (Client-Side Syntax Error)
* **Affected Files**: `apps/core/utils.py`
* **Root Cause**: Python's standard `json.JSONEncoder` outputs `NaN` literals for floating-point NaNs if `allow_nan=True` is not overridden, which causes `SyntaxError: Unexpected token N in JSON` in browser JavaScript `JSON.parse()`.
* **Fix Implemented**: Overrode `SafeJSONEncoder.encode()` with recursive sanitization that translates all `float('nan')` and `float('inf')` values to `None` (which encodes to valid JSON `null`).
* **Regression Test Added**: `tests.test_security_audit.SecurityAuditTests.test_safe_json_encoder_xss_prevention`.
* **Verification Result**: Verified. Outputs `{"nan_val": null}`.

---

### Issue FIX-004: Period Report Growth Calculation Discarded Negative Baselines
* **Severity**: P2 — Medium (MIS Report Accuracy)
* **Affected Files**: `apps/dashboards/views.py`
* **Root Cause**: The period-over-period growth calculation checked `if prev_val is not None and prev_val > 0:`. If the previous period had a negative total (e.g. initial net loss of -100), growth into the next period was omitted (`None`).
* **Fix Implemented**: Changed check to `if prev_val is not None and prev_val != 0:` and calculated growth as `round(((val - prev_val) / abs(prev_val)) * 100, 1)`.
* **Regression Test Added**: `tests.test_financial_accuracy.FinancialAccuracyTests.test_growth_rate_calculations`.
* **Verification Result**: Verified. Growth from `-100` to `50` correctly calculates as `+150.0%`.

---

### Issue FIX-005: Missing Production Cookie & SSL Hardening Settings
* **Severity**: P3 — Low (Security Best Practice)
* **Affected Files**: `AdvancedExcel/settings.py`
* **Root Cause**: `check --deploy` flagged missing HSTS, secure cookies, and clickjacking protection when running in production.
* **Fix Implemented**: Added conditional security hardening block activated whenever `DEBUG=False`:
  - `SESSION_COOKIE_SECURE = True`
  - `CSRF_COOKIE_SECURE = True`
  - `SECURE_CONTENT_TYPE_NOSNIFF = True`
  - `X_FRAME_OPTIONS = 'DENY'`
  - `SECURE_HSTS_SECONDS = 31536000`
* **Verification Result**: Verified. `python manage.py check` passes with 0 issues.
