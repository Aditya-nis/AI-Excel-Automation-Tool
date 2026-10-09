#!/usr/bin/env bash
set -e

echo "=== Vercel Build Started ==="

# 1. Guarantee staticfiles directory exists so Vercel never complains about missing distDir
mkdir -p staticfiles

# 2. Install dependencies using uv (if available) or pip with --break-system-packages for PEP 668 compatibility
if command -v uv &> /dev/null; then
    echo "Installing requirements with uv..."
    uv pip install --system -r requirements.txt
else
    echo "Installing requirements with pip (--break-system-packages)..."
    python3 -m pip install --break-system-packages -r requirements.txt
fi

# 3. Collect static files
echo "Collecting static files into staticfiles/..."
python3 manage.py collectstatic --noinput --clear

# 4. Run database migrations safely (if database is configured)
echo "Running migrations..."
python3 manage.py migrate --noinput || echo "Database migrations deferred (database may be configured via dashboard environment variables)."

echo "=== Vercel Build Completed Successfully ==="
