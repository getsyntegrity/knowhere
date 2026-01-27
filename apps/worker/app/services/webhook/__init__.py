"""
Webhook Configuration

Defines configuration for webhook delivery.
Retry timing is now handled by RabbitMQ DLX queue TTLs (see celery_app.py).
"""

# Retry constants (per design spec FR-03)
MAX_ATTEMPTS = 6  # Initial attempt + 5 retries

# HTTP request configuration
HTTP_TIMEOUT_SECONDS = 10
