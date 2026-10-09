"""
WSGI config for AdvancedExcel project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os
import shutil
from pathlib import Path
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "AdvancedExcel.settings")

# Handle SQLite initialization on Vercel serverless microVM cold-starts
if os.environ.get('VERCEL') and not os.environ.get('DATABASE_URL'):
    base_dir = Path(__file__).resolve().parent.parent
    tmp_db = Path('/tmp/db.sqlite3')
    template_db = base_dir / 'db_template.sqlite3'
    
    if not tmp_db.exists() and template_db.exists():
        try:
            shutil.copyfile(template_db, tmp_db)
        except Exception as e:
            print(f"Error copying template db: {e}")

application = get_wsgi_application()
app = application

# Fail-safe: ensure tables and admin superuser exist on Vercel SQLite
if os.environ.get('VERCEL') and not os.environ.get('DATABASE_URL'):
    try:
        from django.db import connection
        from django.core.management import call_command
        tables = connection.introspection.table_names()
        if 'auth_user' not in tables:
            call_command('migrate', interactive=False)
            
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_pwd = os.environ.get('ADMIN_PASSWORD', 'admin12345')
        admin_user = User.objects.filter(username='admin').first()
        if not admin_user:
            User.objects.create_superuser('admin', 'admin@example.com', admin_pwd)
        else:
            admin_user.set_password(admin_pwd)
            admin_user.save()
    except Exception as exc:
        print(f"Vercel startup database check notice: {exc}")
