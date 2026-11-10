# Gunicorn settings. Every value can be overridden with an environment variable
# so Docker Compose and Kubernetes can tune it without rebuilding the image.
import os

bind = "0.0.0.0:3000"

# gthread = each worker process runs a pool of threads. Requests mostly wait on
# MySQL (I/O), and while a thread waits it releases the Python GIL, so threads
# give concurrency cheaply. Several processes let the pod use more than one CPU.
worker_class = "gthread"
workers = int(os.getenv("GUNICORN_WORKERS", "4"))
threads = int(os.getenv("GUNICORN_THREADS", "4"))   # 4 x 4 = 16 requests in parallel per pod

timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30

# Idle keep-alive connections wait in a poller and cost no thread with gthread,
# so a few seconds of keep-alive saves k6 a reconnect after its 1 s sleep.
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))
backlog = 2048

accesslog = None        # an access log line per request costs CPU at 500 VUs
errorlog = "-"
loglevel = "info"
