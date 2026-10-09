#!/usr/bin/env bash
echo "Building project for Vercel deployment..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

echo "Collecting static files..."
python3 manage.py collectstatic --noinput --clear

echo "Running migrations..."
python3 manage.py migrate --noinput
echo "Vercel build completed successfully!"
