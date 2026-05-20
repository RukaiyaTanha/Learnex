import errno
import logging
import os
import sys

from django.apps import AppConfig
from django.core.management import call_command


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        """Run migrations once on hosted startup when shell access is unavailable."""
        if os.getenv("AUTO_RUN_MIGRATIONS", "1") != "1":
            return

        # Only do this for hosted envs where a managed DB URL is present.
        if not os.getenv("DATABASE_URL"):
            return

        # Avoid recursion / duplication during management commands.
        blocked = {
            "migrate",
            "makemigrations",
            "collectstatic",
            "createsuperuser",
            "shell",
            "dbshell",
            "test",
        }
        if any(cmd in sys.argv for cmd in blocked):
            return

        lock_path = "/tmp/learnex_runtime_migrate.lock"
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                return
            raise

        logger = logging.getLogger(__name__)
        try:
            logger.warning("Running startup migrations (AUTO_RUN_MIGRATIONS=1).")
            call_command("migrate", interactive=False, fake_initial=True, run_syncdb=True, verbosity=1)
            logger.warning("Startup migrations completed.")
        except Exception:
            logger.exception("Startup migrations failed.")
        finally:
            # Optionally seed courses when requested (only runs once per container)
            try:
                if os.getenv("SEED_COURSES") == "1":
                    seed_lock = "/tmp/learnex_seed_courses.lock"
                    if not os.path.exists(seed_lock):
                        logger.warning("Seeding courses as SEED_COURSES=1")
                        call_command("import_course_catalog")
                        open(seed_lock, "w").close()
            except Exception:
                logger.exception("Seeding courses failed.")
