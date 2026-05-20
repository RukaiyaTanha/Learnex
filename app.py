import os
from django.core.wsgi import get_wsgi_application

# Ensure Django settings module is set when Run platforms call `gunicorn app:app`
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

# Standard WSGI application
application = get_wsgi_application()

# Some deployments/tools expect the callable to be named `app`.
app = application
