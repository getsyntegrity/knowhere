"""Webhook services."""
from .dispatcher import WebhookDispatcher, get_webhook_dispatcher

__all__ = ["WebhookDispatcher", "get_webhook_dispatcher"]
