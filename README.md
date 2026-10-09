# AI Power BI + Data Cleaning + MIS Report Engine

Production-oriented enterprise web application combining governed Business Intelligence, verifiable AI-powered data understanding, automated data quality scoring, multi-file consolidation, and Management Information System (MIS) reporting.

---

## Architecture Overview

```
                      ┌───────────────────────────────────────────┐
                      │    Modern Responsive UI (HTML5/CSS3/JS)   │
                      │       Bootstrap Tokens + Chart.js         │
                      └─────────────────────┬─────────────────────┘
                                            │ HTTP / JSON REST APIs
                      ┌─────────────────────▼─────────────────────┐
                      │    Django 5.x Application Framework       │
                      ├───────────────────────────────────────────┤
                      │  • Multi-Tenant Workspaces (RBAC)         │
                      │  • DRF Versioned APIs (/api/v1/)          │
                      │  • Governed Semantic Layer & KPIs         │
                      │  • Tamper-Evident Append-Only Audit Trail │
                      └─────────────┬─────────────────────────────┘
                                    │
       ┌────────────────────────────┼────────────────────────────┐
       ▼                            ▼                            ▼
┌──────────────┐             ┌──────────────┐             ┌──────────────┐
│  Datasets &  │             │ Data Quality │             │ Consolidation│
│ Profiling    │             │ & Cleaning   │             │ & MIS Engine │
├──────────────┤             ├──────────────┤             ├──────────────┤
│ • CSV/XLSX   │             │ • Transparent│             │ • Append/Join│
│ • Parquet vN │             │   Score (0-100)           │ • Cardinality│
│ • Immutable  │             │ • Dry-run diff             │ • Excel/PDF  │
│   Lineage    │             │ • Safe Undo  │             │ • Control Tot│
└──────────────┘             └──────────────┘             └──────────────┘
```

---

## Non-Negotiable Data Integrity Rules

1. **No Fake Data**: Zero hallucinations or invented KPIs. Demonstration datasets are explicitly isolated. Empty views produce honest empty states.
2. **Preserve Original Data**: Uploaded source files are strictly immutable with SHA-256 fingerprinting. All transformations generate new versioned Parquet artifacts (`v1.parquet`, `v2.parquet`, etc.) with parent-child lineage.
3. **Reversible Undo**: Undo restores earlier logical versions without destroying historical records.
4. **Honest AI**: Confidence bands (High $\ge 0.90$, Medium $0.70-0.89$, Low $< 0.70$) are review heuristics backed by empirical evidence. Ambient deterministic fallbacks execute when external LLM keys are absent.
5. **Exact Decimal Precision**: Monetary sums and control totals use Python's `Decimal` with `ROUND_HALF_UP` instead of binary floating point arithmetic.

---

## Core Domain Modules

| App / Module | Purpose |
| :--- | :--- |
| `apps.core` | Decimal arithmetic, safe serialization, growth rate math. |
| `apps.accounts` | User authentication, registration, roles. |
| `apps.workspaces` | Multi-tenant workspace isolation and memberships. |
| `apps.datasets` | Source file uploads, magic byte validation, immutable versioned Parquet storage. |
| `apps.profiling` | Statistical column profiling, quartile/IQR outlier detection, candidate keys. |
| `apps.understanding` | Calibrated AI semantic role inferences with evidence traces. |
| `apps.data_quality` | Dedicated Data Quality Center with 4-component scoring and 1-click quick fixes. |
| `apps.cleaning` | Versioned transformation engine (trim, casing, normalize dates, types, deduplication, missing values, outliers) with dry-run preview and undo. |
| `apps.consolidation` | Multi-file append and join operations with cardinality explosion warnings and control-total reconciliation. |
| `apps.semantic_model` | Certified business dimensions, measures, formulas, and KPI catalog. |
| `apps.ask_data` | Natural language conversational analytics compiler with deterministic execution and chart payloads. |
| `apps.reports` | Parameterized MIS report builder with Excel (.xlsx), CSV, and PDF exports. |
| `apps.automation` | Saved cleaning recipes and scheduled recurring workflows with schema-drift protection. |
| `apps.audit` | Append-only governance audit trail capturing all operational events. |
| `apps.api` | REST API viewsets under `/api/v1/`. |

---

## 16 Application Screens

1. **Login & Account Management**: `/accounts/login/`, `/accounts/register/`
2. **Workspace Home & Analytics Dashboard**: `/`
3. **Data Upload & File Inventory**: `/upload/`
4. **Dataset Preview & Profiling**: `/datasets/<id>/`
5. **AI Understanding Review**: `/datasets/<id>/understanding/`
6. **Data Quality Center**: `/datasets/<id>/quality/`
7. **Transformation History & Undo**: `/datasets/<id>/transformations/`
8. **Multi-File Consolidation & Reconciliation**: `/consolidation/`
9. **Semantic Model & KPI Catalog**: `/semantic-models/`
10. **Ask Your Data (Conversational Analytics)**: `/ask-data/`
11. **MIS Report Builder**: `/reports/`
12. **Saved Rules & Recurring Workflows**: `/automation/`
13. **Background Job Monitor**: `/jobs/`
14. **Security, Roles & Audit Trail**: `/audit/`
15. **Application & Workspace Settings**: `/settings/`

---

## REST API Endpoints (`/api/v1/`)

* `/api/v1/workspaces/` (List, create, switch active workspace)
* `/api/v1/files/` (Upload, validate, inspect sheets)
* `/api/v1/datasets/` (Preview, sort, filter, versions, undo, restore)
* `/api/v1/quality/` (Quality report, issues, quick_fix)
* `/api/v1/understanding/` (Inferred roles, review, override)
* `/api/v1/cleaning/` (Preview dry-run, execute, recipes)
* `/api/v1/consolidation/` (Cardinality preview, execute merge, reconcile)
* `/api/v1/semantic-models/` (Auto-generate, certified metrics)
* `/api/v1/ask-data/` (Conversational analytics query runner)
* `/api/v1/reports/` (Generate MIS report, download Excel/PDF/CSV)
* `/api/v1/automation/` (Schedule workflows, trigger runs)
* `/api/v1/jobs/` (Execution logs and status)
* `/api/v1/audit/` (Governance audit records)

---

## Local Development & Setup

### 1. Prerequisites
* Python 3.10+ (tested and verified with Python 3.13)
* Virtual environment (recommended)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```bash
# Windows PowerShell
Copy-Item .env.example .env

# Linux / macOS
cp .env.example .env
```

### 4. Database Migrations
```bash
python manage.py migrate
```

### 5. Create Superuser (Admin)
```bash
python manage.py createsuperuser
```

### 6. Run Development Server
```bash
python manage.py runserver 8000
```
Visit `http://localhost:8000/` in your browser.

---

## Running Automated Tests

Run the full automated test suite covering data integrity, decimal precision, undo/lineage, cardinality safeguards, schema drift, and MIS exports:

```bash
python manage.py test apps.core apps.datasets apps.cleaning apps.consolidation apps.automation apps.reports apps.ask_data
```

**Test Status**: 14 tests run, 14 passing (100% OK).
