"""
Webhook Queue Configuration

Defines RabbitMQ topology for webhook delivery with leveled retry queues.
Uses Dead Letter Exchanges (DLX) for non-blocking exponential backoff.
"""

# Exchange names
WEBHOOK_DIRECT_EXCHANGE = "webhook.direct"
WEBHOOK_RETRY_EXCHANGE = "webhook.retry"
WEBHOOK_DLX_EXCHANGE = "webhook.dlx"

# Queue names
WEBHOOK_WORK_QUEUE = "q.webhook.work"
WEBHOOK_DEAD_QUEUE = "q.webhook.dead"

# Retry queue configuration with TTLs
# Each level doubles the wait time, matching the design spec
RETRY_LEVELS = [
    {"name": "q.webhook.wait.1m", "ttl_ms": 60_000, "routing_key": "wait.1m"},
    {"name": "q.webhook.wait.10m", "ttl_ms": 600_000, "routing_key": "wait.10m"},
    {"name": "q.webhook.wait.30m", "ttl_ms": 1_800_000, "routing_key": "wait.30m"},
    {"name": "q.webhook.wait.2h", "ttl_ms": 7_200_000, "routing_key": "wait.2h"},
    {"name": "q.webhook.wait.6h", "ttl_ms": 21_600_000, "routing_key": "wait.6h"},
]

# Retry constants
MAX_ATTEMPTS = 6  # Initial + 5 retries
BASE_DELAY_SECONDS = 60
JITTER_FACTOR = 0.1  # ±10% as per design spec

# HTTP request configuration
HTTP_TIMEOUT_SECONDS = 10
