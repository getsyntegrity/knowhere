"""
Webhook Configuration

Defines retry configuration for webhook delivery with exponential backoff.
Celery handles queue routing - these are just retry timing constants.
"""

# Retry constants (per design spec FR-03)
MAX_ATTEMPTS = 6  # Initial attempt + 5 retries
BASE_DELAY_SECONDS = 60
JITTER_FACTOR = 0.1  # ±10% jitter

# HTTP request configuration
HTTP_TIMEOUT_SECONDS = 10

# Retry delays matching design spec schedule (used by dispatcher)
RETRY_DELAYS = [60, 600, 1800, 7200, 21600]  # 1m, 10m, 30m, 2h, 6h
