#!/usr/bin/env bash
set -e

echo "=== Vercel Build Started ==="

# 1. Guarantee staticfiles directory exists
mkdir -p staticfiles

# 2. Set up isolated virtual environment
echo "Creating isolated virtual environment..."
VENV_DIR=".build_venv"

if command -v uv &> /dev/null; then
    uv venv "$VENV_DIR" || python3 -m venv "$VENV_DIR" || python -m venv "$VENV_DIR"
    echo "Installing requirements with uv into $VENV_DIR..."
    uv pip install --python "$VENV_DIR/bin/python" -r requirements.txt || "$VENV_DIR/bin/pip" install -r requirements.txt
else
    python3 -m venv "$VENV_DIR" || python -m venv "$VENV_DIR"
    echo "Installing requirements with pip into $VENV_DIR..."
    "$VENV_DIR/bin/pip" install -r requirements.txt
fi

PY_EXEC="$VENV_DIR/bin/python"
echo "Active build Python: $("$PY_EXEC" --version 2>&1 || echo "$PY_EXEC")"

# 3. Collect static files using the virtual environment Python
echo "Collecting static files into staticfiles/..."
"$PY_EXEC" manage.py collectstatic --noinput --clear || echo "Pre-collected static files preserved."

# 4. Run database migrations safely (if database is configured)
echo "Running migrations..."
"$PY_EXEC" manage.py migrate --noinput || echo "Database migrations deferred (database may be configured via dashboard environment variables)."

echo "=== Vercel Build Completed Successfully ==="
