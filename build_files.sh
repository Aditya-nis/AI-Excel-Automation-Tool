#!/usr/bin/env bash
set -e

echo "=== Vercel Build Started ==="

# 1. Guarantee staticfiles directory exists so Vercel never complains about missing distDir
mkdir -p staticfiles

# 2. Create and activate an isolated virtual environment
# This completely eliminates PEP 668 errors and ensures dependency installation
# and manage.py run against the exact same Python environment.
echo "Creating isolated virtual environment..."
if command -v uv &> /dev/null; then
    uv venv .build_venv || python3 -m venv .build_venv
    # shellcheck disable=SC1091
    source .build_venv/bin/activate
    echo "Installing requirements with uv into virtual environment..."
    uv pip install -r requirements.txt || pip install -r requirements.txt
else
    python3 -m venv .build_venv || python -m venv .build_venv
    # shellcheck disable=SC1091
    source .build_venv/bin/activate
    echo "Installing requirements with pip into virtual environment..."
    pip install -r requirements.txt
fi

echo "Active build Python: $(which python) ($(python --version))"

# 3. Collect static files using the virtualenv python
echo "Collecting static files into staticfiles/..."
python manage.py collectstatic --noinput --clear

# 4. Run database migrations safely (if database is configured)
echo "Running migrations..."
python manage.py migrate --noinput || echo "Database migrations deferred (database may be configured via dashboard environment variables)."

echo "=== Vercel Build Completed Successfully ==="


