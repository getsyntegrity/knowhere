"""
Sync message publisher for Celery worker (gevent pool).

Uses one bounded process-wide publisher loop so worker greenlets do not open
their own RabbitMQ connection/channel pairs. Terminal messages are confirmed
by the background publisher; progress updates are best-effort and are dropped
when the local queue backs up.
"""
import json
import os
import socket
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import gevent
from gevent.event import AsyncResult, Event
from gevent.lock import Semaphore
from gevent.queue import Empty, Full, Queue as GeventQueue
from kombu import Connection, Exchange, Producer, Queue
from loguru import logger

sys.set_int_max_str_digits(10000)

from shared.core.config import app_config
from shared.core.config.messaging import messaging_config
from shared.core.logging import LogEvent
from shared.models.schemas.messages import (
    BaseMessage,
    JobFailureMessage,
    JobProgressUpdateMessage,
    JobResultMessage,
    JobStatusUpdateMessage,
)
from shared.services.messaging.monitoring import message_monitoring


@dataclass
class _PublishRequest:
    message: BaseMessage
    routing_key: str
    queue_name: str
    priority: int
    wait_for_confirmation: bool
    result: Optional[AsyncResult] = None


class SyncMessagePublisher:
    """Kombu-backed publisher owned by the background publisher loop."""

    def __init__(self):
        self._connection: Optional[Connection] = None
        self._producer: Optional[Producer] = None
        self._exchange: Optional[Exchange] = None
        self._queues: dict[str, Queue] = {}

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

    def _build_queue(self, queue_name: str, routing_key: str) -> Queue:
        queue_config = messaging_config.get_queue_config(queue_name)
        return Queue(
            queue_name,
            exchange=self._exchange,
            routing_key=routing_key,
            durable=queue_config["durable"],
            auto_delete=queue_config["auto_delete"],
            exclusive=queue_config["exclusive"],
            queue_arguments=queue_config["queue_arguments"],
        )

    def _declare_topology(self) -> None:
        assert self._connection is not None
        assert self._exchange is not None

        self._exchange.maybe_bind(self._connection)
        self._exchange.declare()

        queues: dict[str, Queue] = {}
        for message_type in (
            "job_status_update",
            "job_progress_update",
            "job_result",
            "job_failure",
        ):
            routing_key = self._get_routing_key(message_type)
            queue_name = self._get_queue_name(message_type)
            queue = self._build_queue(queue_name, routing_key)
            queue.maybe_bind(self._connection)
            queue.declare()
            queues[queue_name] = queue

        self._queues = queues

    def _reset_connection(self, close_existing: bool = False) -> None:
        connection = self._connection
        if close_existing and connection is not None:
            try:
                connection.close()
                logger.info("Sync publisher connection closed after publish failure")
            except Exception as close_error:
                logger.warning(f"Failed to close broken sync publisher connection: {close_error}")

        self._connection = None
        self._producer = None
        self._exchange = None
        self._queues = {}

    def _ensure_connection(self) -> None:
        if self._connection is not None and self._connection.connected:
            return

        broker_url = app_config.get_celery_broker_url()
        connection_name = f"worker-publisher@{socket.gethostname()}-{os.getpid()}"
        connection = Connection(
            broker_url,
            heartbeat=30,
            transport_options={"client_properties": {"connection_name": connection_name}},
        )
        connection.ensure_connection(max_retries=3, interval_start=1, interval_step=2)

        exchange = Exchange(
            messaging_config.EXCHANGE_NAME,
            type=messaging_config.EXCHANGE_TYPE,
            durable=True,
            auto_delete=False,
        )
        channel = connection.channel()
        producer = Producer(channel, exchange=exchange, serializer="json")

        self._connection = connection
        self._exchange = exchange
        self._producer = producer
        self._declare_topology()

        logger.bind(event=LogEvent.NETWORK_AMQP_CONNECT.value).info(
            f"Sync publisher connected: connection_name={connection_name}"
        )

    def publish_immediately(
        self,
        message: BaseMessage,
        routing_key: str,
        queue_name: str,
        priority: Optional[int] = None,
    ) -> bool:
        max_retries = 2
        for attempt in range(max_retries):
            try:
                self._ensure_connection()
                assert self._producer is not None

                effective_priority = priority
                if effective_priority is None:
                    effective_priority = messaging_config.get_message_priority(
                        message.message_type
                    )

                message_dict = message.model_dump(mode="json")
                message_body = json.dumps(message_dict, ensure_ascii=False)

                self._producer.publish(
                    message_body,
                    routing_key=routing_key,
                    delivery_mode=2,
                    priority=effective_priority,
                    content_type="application/json",
                    content_encoding="utf-8",
                )

                message_monitoring.record_message_published(
                    message.message_type, message.job_id, True
                )
                logger.debug(
                    f"Message published: {message.message_type}, job_id={message.job_id}"
                )
                return True

            except Exception as e:
                self._reset_connection(close_existing=True)

                if attempt < max_retries - 1:
                    logger.bind(event=LogEvent.NETWORK_AMQP_PUBLISH_ERROR.value).warning(
                        f"Publish failed (attempt {attempt + 1}/{max_retries}), "
                        f"reconnecting: message_type={message.message_type}, "
                        f"job_id={message.job_id}, error={e}"
                    )
                    continue

                logger.bind(event=LogEvent.NETWORK_AMQP_PUBLISH_ERROR.value).error(
                    f"Publish failed after {max_retries} attempts: "
                    f"message_type={message.message_type}, job_id={message.job_id}, error={e}"
                )
                message_monitoring.record_message_published(
                    message.message_type, message.job_id, False
                )
                return False
        return False

    def close(self) -> None:
        if self._connection is None:
            return
        try:
            self._connection.close()
            logger.info("Sync message publisher connection closed")
        except Exception as close_error:
            logger.warning(f"Failed to close sync message publisher connection: {close_error}")
        finally:
            self._reset_connection(close_existing=False)


class ProcessWideSyncMessagePublisher:
    """Bounded process-wide publisher facade used by worker greenlets."""

    def __init__(
        self,
        max_queue_size: Optional[int] = None,
        progress_drop_threshold: Optional[int] = None,
        enqueue_timeout: Optional[float] = None,
        publish_timeout: Optional[float] = None,
    ):
        self._publisher = SyncMessagePublisher()
        self._max_queue_size = max_queue_size or int(
            os.getenv("SYNC_PUBLISHER_QUEUE_SIZE", "256")
        )
        self._progress_drop_threshold = progress_drop_threshold
        if self._progress_drop_threshold is None:
            threshold_ratio = float(
                os.getenv("SYNC_PUBLISHER_PROGRESS_DROP_RATIO", "0.75")
            )
            self._progress_drop_threshold = max(
                1, int(self._max_queue_size * threshold_ratio)
            )
        self._enqueue_timeout = enqueue_timeout or float(
            os.getenv("SYNC_PUBLISHER_ENQUEUE_TIMEOUT_SECONDS", "5")
        )
        self._publish_timeout = publish_timeout or float(
            os.getenv("SYNC_PUBLISHER_CONFIRM_TIMEOUT_SECONDS", "30")
        )

        self._queue: GeventQueue[_PublishRequest] = GeventQueue(
            maxsize=self._max_queue_size
        )
        self._stop_event = Event()
        self._loop_guard = Semaphore()
        self._worker_greenlet: Optional[gevent.Greenlet] = None
        self._ensure_worker_loop()

    def _ensure_worker_loop(self) -> None:
        with self._loop_guard:
            if self._worker_greenlet is not None and not self._worker_greenlet.dead:
                return
            self._stop_event.clear()
            self._worker_greenlet = gevent.spawn(self._publisher_loop)
            logger.info(
                "Started process-wide sync publisher loop: "
                f"queue_size={self._max_queue_size}, "
                f"progress_drop_threshold={self._progress_drop_threshold}"
            )

    def _publisher_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                request = self._queue.get(timeout=1.0)
            except Empty:
                continue

            success = self._publisher.publish_immediately(
                request.message,
                request.routing_key,
                request.queue_name,
                priority=request.priority,
            )

            if request.result is not None and not request.result.ready():
                request.result.set(success)

    def _queue_backlogged_for_progress(self) -> bool:
        return self._queue.qsize() >= self._progress_drop_threshold

    def _submit(
        self,
        message: BaseMessage,
        routing_key: str,
        queue_name: str,
        priority: int,
        wait_for_confirmation: bool,
        best_effort: bool,
    ) -> bool:
        self._ensure_worker_loop()

        if best_effort and self._queue_backlogged_for_progress():
            logger.warning(
                "Dropping progress update due to local publisher backlog: "
                f"job_id={message.job_id}, queue_depth={self._queue.qsize()}"
            )
            message_monitoring.record_message_published(
                message.message_type, message.job_id, False
            )
            return False

        result = AsyncResult() if wait_for_confirmation else None
        request = _PublishRequest(
            message=message,
            routing_key=routing_key,
            queue_name=queue_name,
            priority=priority,
            wait_for_confirmation=wait_for_confirmation,
            result=result,
        )

        try:
            if best_effort:
                self._queue.put_nowait(request)
                return True

            self._queue.put(request, timeout=self._enqueue_timeout)
        except Full:
            logger.warning(
                "Sync publisher queue full, publish rejected: "
                f"message_type={message.message_type}, job_id={message.job_id}"
            )
            message_monitoring.record_message_published(
                message.message_type, message.job_id, False
            )
            return False

        if not wait_for_confirmation:
            return True

        assert result is not None
        try:
            return bool(result.get(timeout=self._publish_timeout))
        except Exception as exc:
            logger.error(
                "Timed out waiting for sync publisher confirmation: "
                f"message_type={message.message_type}, job_id={message.job_id}, error={exc}"
            )
            message_monitoring.record_message_published(
                message.message_type, message.job_id, False
            )
            return False

    def publish_status_update(
        self,
        job_id: str,
        status: str,
        trigger: str,
        previous_status: Optional[str] = None,
        operator_id: Optional[str] = None,
        operator_type: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        message = JobStatusUpdateMessage(
            job_id=job_id,
            status=status,
            previous_status=previous_status,
            trigger=trigger,
            operator_id=operator_id,
            operator_type=operator_type,
            metadata=metadata,
        )
        return self._submit(
            message,
            self._publisher._get_routing_key("job_status_update"),
            self._publisher._get_queue_name("job_status_update"),
            messaging_config.get_message_priority("job_status_update"),
            wait_for_confirmation=True,
            best_effort=False,
        )

    def publish_progress_update(
        self,
        job_id: str,
        progress: int,
        message_text: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        message = JobProgressUpdateMessage(
            job_id=job_id,
            progress=progress,
            message=message_text,
            metadata=metadata,
        )
        return self._submit(
            message,
            self._publisher._get_routing_key("job_progress_update"),
            self._publisher._get_queue_name("job_progress_update"),
            messaging_config.get_message_priority("job_progress_update"),
            wait_for_confirmation=False,
            best_effort=True,
        )

    def publish_result(
        self,
        job_id: str,
        chunks_job_id: str,
        result_s3_key: str,
        checksum: str,
        zip_size: int,
        stored_count: int = 0,
        kb_records: Optional[List[Dict[str, Any]]] = None,
        statistics: Optional[Dict[str, Any]] = None,
        delivery_mode: str = "url",
        add_dir: Optional[str] = None,
    ) -> bool:
        message = JobResultMessage(
            job_id=job_id,
            chunks_job_id=chunks_job_id,
            result_s3_key=result_s3_key,
            checksum=checksum,
            zip_size=zip_size,
            stored_count=stored_count,
            kb_records=kb_records,
            statistics=statistics,
            delivery_mode=delivery_mode,
            add_dir=add_dir,
        )
        return self._submit(
            message,
            self._publisher._get_routing_key("job_result"),
            self._publisher._get_queue_name("job_result"),
            messaging_config.get_message_priority("job_result"),
            wait_for_confirmation=True,
            best_effort=False,
        )

    def publish_failure(
        self,
        job_id: str,
        error_message: str,
        error_code: str = "UNKNOWN",
        error_type: Optional[str] = None,
        stack_trace: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        message = JobFailureMessage(
            job_id=job_id,
            error_code=error_code,
            error_message=error_message,
            error_type=error_type,
            stack_trace=stack_trace,
            metadata=metadata,
        )
        return self._submit(
            message,
            self._publisher._get_routing_key("job_failure"),
            self._publisher._get_queue_name("job_failure"),
            messaging_config.get_message_priority("job_failure"),
            wait_for_confirmation=True,
            best_effort=False,
        )

    def close(self) -> None:
        with self._loop_guard:
            self._stop_event.set()
            worker_greenlet = self._worker_greenlet
            self._worker_greenlet = None

        if worker_greenlet is not None and not worker_greenlet.dead:
            worker_greenlet.kill(block=True, timeout=1)

        while True:
            try:
                request = self._queue.get_nowait()
            except Empty:
                break
            if request.result is not None and not request.result.ready():
                request.result.set(False)

        self._publisher.close()


_process_publisher: Optional[ProcessWideSyncMessagePublisher] = None
_process_publisher_lock = Semaphore()


def get_sync_message_publisher() -> ProcessWideSyncMessagePublisher:
    """Get the bounded process-wide sync publisher for this worker process."""
    global _process_publisher
    with _process_publisher_lock:
        if _process_publisher is None:
            _process_publisher = ProcessWideSyncMessagePublisher()
        return _process_publisher


def close_sync_message_publisher() -> None:
    """Close and clear the process-wide sync publisher."""
    global _process_publisher
    with _process_publisher_lock:
        publisher = _process_publisher
        _process_publisher = None
    if publisher is None:
        return
    publisher.close()
