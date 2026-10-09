#!/usr/bin/env bash
set -e

echo "=== Vercel Build Started ==="

# 1. Guarantee staticfiles directory exists so Vercel never complains about missing distDir
mkdir -p staticfiles

# 2. Check for best available python version
if command -v python3.11 &> /dev/null; then
    PY_BIN=python3.11
elif command -v python3.12 &> /dev/null; then
    PY_BIN=python3.12
elif command -v python3 &> /dev/null; then
    PY_BIN=python3
else
    PY_BIN=python
fi

echo "Selected Python binary: $($PY_BIN --version 2>&1 || echo $PY_BIN)"

# 3. Install dependencies using uv (if available) or pip with --break-system-packages
if command -v uv &> /dev/null; then
    echo "Installing requirements with uv..."
    uv pip install --system --python "$PY_BIN" -r requirements.txt || uv pip install --system -r requirements.txt
else
    echo "Installing requirements with pip (--break-system-packages)..."
    $PY_BIN -m pip install --break-system-packages -r requirements.txt || python3 -m pip install -r requirements.txt
fi

# 4. Collect static files
echo "Collecting static files into staticfiles/..."
$PY_BIN manage.py collectstatic --noinput --clear

# 5. Run database migrations safely (if database is configured)
echo "Running migrations..."
$PY_BIN manage.py migrate --noinput || echo "Database migrations deferred (database may be configured via dashboard environment variables)."

echo "=== Vercel Build Completed Successfully ==="

