"""
Sync message publisher for Celery worker (gevent pool).
Uses Kombu (already a Celery dependency) for sync AMQP operations.
Under gevent, Kombu socket operations become cooperative automatically.
API service continues using async MessagePublisher with aio-pika.
"""
import json
import sys
from typing import Any, Dict, List, Optional

from kombu import Connection, Exchange, Producer, Queue
from loguru import logger

sys.set_int_max_str_digits(10000)

from shared.core.config import app_config
from shared.core.config.messaging import messaging_config
from shared.models.schemas.messages import (
    BaseMessage,
    JobFailureMessage,
    JobProgressUpdateMessage,
    JobResultMessage,
    JobStatusUpdateMessage,
)
from shared.services.messaging.monitoring import message_monitoring


class SyncMessagePublisher:
    """Sync message publisher using Kombu for gevent worker."""

    def __init__(self):
        self._connection: Optional[Connection] = None
        self._producer: Optional[Producer] = None
        self._exchange: Optional[Exchange] = None

    def _ensure_connection(self):
        if self._connection is not None and self._connection.connected:
            return

        broker_url = app_config.get_celery_broker_url()
        self._connection = Connection(broker_url, heartbeat=600)
        self._connection.ensure_connection(max_retries=3, interval_start=1, interval_step=2)

        self._exchange = Exchange(
            messaging_config.EXCHANGE_NAME,
            type=messaging_config.EXCHANGE_TYPE,
            durable=True,
            auto_delete=False,
        )

        channel = self._connection.channel()
        self._producer = Producer(channel, exchange=self._exchange, serializer="json")
        logger.info("Sync message publisher connected to broker")

    def _get_routing_key(self, message_type: str) -> str:
        routing_keys = {
            "job_status_update": messaging_config.ROUTING_KEY_STATUS_UPDATE,
            "job_progress_update": messaging_config.ROUTING_KEY_PROGRESS_UPDATE,
            "job_result": messaging_config.ROUTING_KEY_RESULT,
            "job_failure": messaging_config.ROUTING_KEY_FAILURE,
        }
        return routing_keys.get(message_type, messaging_config.ROUTING_KEY_STATUS_UPDATE)

    def _get_queue_name(self, message_type: str) -> str:
        queue_names = {
            "job_status_update": messaging_config.QUEUE_STATUS_UPDATES,
            "job_progress_update": messaging_config.QUEUE_PROGRESS_UPDATES,
            "job_result": messaging_config.QUEUE_RESULTS,
            "job_failure": messaging_config.QUEUE_FAILURES,
        }
        return queue_names.get(message_type, messaging_config.QUEUE_STATUS_UPDATES)

    def _publish(self, message: BaseMessage, routing_key: str, queue_name: str, priority: Optional[int] = None) -> bool:
        try:
            self._ensure_connection()

            if priority is None:
                priority = messaging_config.get_message_priority(message.message_type)

            # Declare queue and bind to exchange
            queue = Queue(
                queue_name,
                exchange=self._exchange,
                routing_key=routing_key,
                durable=True,
                queue_arguments={"x-max-priority": messaging_config.QUEUE_MAX_PRIORITY},
            )
            queue.maybe_bind(self._connection)
            queue.declare()

            message_dict = message.model_dump(mode="json")
            message_body = json.dumps(message_dict, ensure_ascii=False)

            self._producer.publish(
                message_body,
                routing_key=routing_key,
                delivery_mode=2,
                priority=priority,
                content_type="application/json",
                content_encoding="utf-8",
            )

            message_monitoring.record_message_published(message.message_type, message.job_id, True)
            logger.debug(f"Message published: {message.message_type}, job_id={message.job_id}")
            return True

        except Exception as e:
            logger.error(f"Message publish failed: {message.message_type}, job_id={message.job_id}, error={e}")
            message_monitoring.record_message_published(message.message_type, message.job_id, False)
            # Reset connection on failure
            logger.warning("Sync message publisher connection reset due to publish failure")
            self._connection = None
            self._producer = None
            return False

    def publish_status_update(self, job_id: str, status: str, trigger: str, previous_status: Optional[str] = None, operator_id: Optional[str] = None, operator_type: str = "system", metadata: Optional[Dict[str, Any]] = None) -> bool:
        message = JobStatusUpdateMessage(
            job_id=job_id, status=status, previous_status=previous_status,
            trigger=trigger, operator_id=operator_id, operator_type=operator_type, metadata=metadata,
        )
        return self._publish(message, self._get_routing_key("job_status_update"), self._get_queue_name("job_status_update"))

    def publish_progress_update(self, job_id: str, progress: int, message_text: str = "", metadata: Optional[Dict[str, Any]] = None) -> bool:
        message = JobProgressUpdateMessage(
            job_id=job_id, progress=progress, message=message_text, metadata=metadata,
        )
        return self._publish(message, self._get_routing_key("job_progress_update"), self._get_queue_name("job_progress_update"))

    def publish_result(self, job_id: str, chunks_job_id: str, result_s3_key: str, checksum: str, zip_size: int, stored_count: int = 0, kb_records: Optional[List[Dict[str, Any]]] = None, statistics: Optional[Dict[str, Any]] = None, delivery_mode: str = "url", add_dir: Optional[str] = None) -> bool:
        message = JobResultMessage(
            job_id=job_id, chunks_job_id=chunks_job_id, result_s3_key=result_s3_key,
            checksum=checksum, zip_size=zip_size, stored_count=stored_count,
            kb_records=kb_records, statistics=statistics, delivery_mode=delivery_mode, add_dir=add_dir,
        )
        return self._publish(message, self._get_routing_key("job_result"), self._get_queue_name("job_result"))

    def publish_failure(self, job_id: str, error_message: str, error_code: str = "UNKNOWN", error_type: Optional[str] = None, stack_trace: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        message = JobFailureMessage(
            job_id=job_id, error_code=error_code, error_message=error_message,
            error_type=error_type, stack_trace=stack_trace, metadata=metadata,
        )
        return self._publish(message, self._get_routing_key("job_failure"), self._get_queue_name("job_failure"))

    def close(self):
        if self._connection:
            try:
                self._connection.close()
                logger.info("Sync message publisher connection closed")
            except Exception:
                pass
            self._connection = None
            self._producer = None


_sync_message_publisher: Optional[SyncMessagePublisher] = None


def get_sync_message_publisher() -> SyncMessagePublisher:
    """Get sync message publisher instance (singleton)."""
    global _sync_message_publisher
    if _sync_message_publisher is None:
        _sync_message_publisher = SyncMessagePublisher()
    return _sync_message_publisher
