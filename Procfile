web: bash -lc "python manage.py migrate --noinput --fake-initial && gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --log-file -"
