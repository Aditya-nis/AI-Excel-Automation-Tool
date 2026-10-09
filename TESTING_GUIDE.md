# Comprehensive Testing Guide

This guide outlines how to run automated unit, integration, security, and end-to-end tests for the **AI Power BI + Data Cleaning + MIS Report Engine**.

---

## 1. Environment Setup

Ensure your local virtual environment is active and all dependencies are installed:

```bash
# Activate virtual environment
# Windows:
.\env\Scripts\activate
# Linux/macOS:
source env/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## 2. Running Automated Tests

Django's test runner automatically executes tests against an isolated, in-memory/temporary test database. Real application data is never touched or modified.

### Run All 42 Tests
```bash
python manage.py test
```

### Run Specific Test Modules

#### 1. End-to-End Business Lifecycle Test
Tests file upload, ingestion, parquet versioning, data cleaning, executive MIS report generation, and natural-language query execution:
```bash
python manage.py test tests.test_e2e_workflow
```

#### 2. Security Audit & Isolation Tests
Tests workspace isolation, unauthenticated redirects, magic-byte validation, and safe JSON serialization:
```bash
python manage.py test tests.test_security_audit
```

#### 3. Financial & Arithmetic Accuracy Tests
Tests accounting negative number parsing, division-by-zero protection, and growth rate calculations:
```bash
python manage.py test tests.test_financial_accuracy
```

#### 4. App-Specific Unit Tests
```bash
python manage.py test apps.datasets
python manage.py test apps.cleaning
python manage.py test apps.reports
python manage.py test apps.dashboards
```

---

## 3. System & Deployment Checks

Run Django's built-in system consistency checks:
```bash
# Basic system integrity check
python manage.py check

# Check for unmigrated database models
python manage.py makemigrations --check --dry-run

# Production security deployment audit
python manage.py check --deploy
```

---

## 4. Test Isolation & Data Guarantees

- **No Data Loss**: The test runner creates and destroys its own test database `test_db.sqlite3`.
- **Deterministic Fixtures**: All tests use controlled synthetic datasets with known mathematical expectations.
- **Auditable Lineage**: Ingestion and transformation tests verify that source files are never overwritten and that version histories remain immutable.
