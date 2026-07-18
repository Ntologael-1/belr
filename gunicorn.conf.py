# gunicorn.conf.py
bind = "127.0.0.1:8000"
workers = 3
worker_class = "sync"
timeout = 120
keepalive = 5
accesslog = "/var/log/belr/gunicorn_access.log"
errorlog = "/var/log/belr/gunicorn_error.log"
loglevel = "info"