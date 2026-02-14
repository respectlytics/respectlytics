"""
Gunicorn configuration file for Respectlytics
"""
import os
import multiprocessing

# Server Socket (bind is set per-environment below)
backlog = 2048

# Worker Processes
# Using threaded workers (gthread) for better I/O concurrency with database queries
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "gthread"
threads = 3  # Each worker handles 3 concurrent requests (use 4 for 2+ CPUs)
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
timeout = 30
keepalive = 2

# Development vs Production
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

if DEBUG:
    # Development settings
    bind = "127.0.0.1:8080"  # Localhost only for security
    workers = 1
    threads = 3
    reload = True  # Auto-reload on code changes
    loglevel = 'info'
    # Disable access log - use Django's middleware logging instead (has API key sanitization)
    accesslog = None
    errorlog = '-'   # Log to stderr
    # Disable preload on macOS dev - fork() crashes with threaded scheduler
    preload_app = False
else:
    # Production settings (DigitalOcean App Platform / 1 vCPU / 512MB RAM)
    # 1 worker + 3 threads = 3 concurrent requests, low memory footprint
    # Scale workers when upgrading to 2+ vCPU / 1GB+ RAM
    bind = "0.0.0.0:8080"  # Accept connections from load balancer
    workers = 1
    threads = 3
    reload = False
    loglevel = 'warning'
    # Disable access log - use Django's middleware logging instead (has API key sanitization)
    accesslog = None
    errorlog = '-'  # Log to stderr for App Platform log aggregation
    # Enable preload in production - scheduler runs once in master
    preload_app = True
    # Required for DigitalOcean App Platform (Docker container temp dir issues)
    worker_tmp_dir = '/dev/shm'

# Logging
# Note: accesslog disabled in favor of Django's RequestLoggingMiddleware
# which sanitizes API keys through SanitizeAppKeyFilter

# Process Naming
proc_name = 'respectlytics'

# Server Mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (for production)
# keyfile = '/path/to/keyfile'
# certfile = '/path/to/certfile'
