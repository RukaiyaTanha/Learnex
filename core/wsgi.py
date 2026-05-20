"""
WSGI config for core project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import errno

from django.core.wsgi import get_wsgi_application
from django.core.management import call_command

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')


def _maybe_run_startup_migrations() -> None:
	"""Run DB migrations once per container boot in hosted environments."""
	if os.getenv("AUTO_RUN_MIGRATIONS", "1") != "1":
		return

	# Only auto-migrate when a managed DB URL is present (typical for Render).
	if not os.getenv("DATABASE_URL"):
		return

	lock_path = "/tmp/learnex_startup_migrate.lock"
	try:
		fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
		os.close(fd)
	except OSError as exc:
		if exc.errno == errno.EEXIST:
			return
		raise

	call_command("migrate", interactive=False, fake_initial=True, run_syncdb=True, verbosity=1)


_maybe_run_startup_migrations()

application = get_wsgi_application()
