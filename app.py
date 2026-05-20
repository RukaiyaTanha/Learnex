import os
import errno
from django.core.wsgi import get_wsgi_application
from django.core.management import call_command

# Ensure Django settings module is set when Run platforms call `gunicorn app:app`
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")


def _maybe_run_startup_migrations() -> None:
	if os.getenv("AUTO_RUN_MIGRATIONS", "1") != "1":
		return
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

# Standard WSGI application
application = get_wsgi_application()

# Some deployments/tools expect the callable to be named `app`.
app = application
