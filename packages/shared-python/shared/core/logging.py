import logging
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum
from typing import Any, Dict

from celery import Task
from loguru import logger

LOG_CONTEXT_KEY = "_log_context"
_log_context: ContextVar[Dict[str, Any]] = ContextVar("log_context", default={})

class LogEvent(Enum):
    """
    Registry of canonical event names for structured logging.

    Event names follow the pattern: domain.action.result
    - Use these constants instead of raw strings
    - Add new events to this registry in the same PR
    - Event names are stable; message text can evolve
    """
    # HTTP events
    HTTP_REQUEST_START = "http.request.start"
    HTTP_REQUEST_COMPLETE = "http.request.complete"

    # Exception events
    EXCEPTION_CLIENT = "exception.client"  # 4xx errors
    EXCEPTION_SYSTEM = "exception.system"  # 5xx errors

    # Worker events
    WORKER_TASK_START = "worker.task.start"
    WORKER_TASK_COMPLETE = "worker.task.complete"
    WORKER_TASK_RETRY = "worker.task.retry"
    WORKER_TASK_FAILURE = "worker.task.failure"

    # Correlation diagnostics
    CORRELATION_REQUEST_ID_MISSING = "correlation.request_id_missing"

    # System events
    LOGGING_CONFIGURED = "logging.configured"
    APP_LOG = "app.log"

    S3_WEBHOOK_EVENT = "s3.webhook"


@contextmanager
def log_context(**kwargs):
    """
    Global context helper backed by ContextVar + Loguru contextualize().
    """
    current = _log_context.get()
    merged = {**current, **kwargs}
    token = _log_context.set(merged)
    try:
        with logger.contextualize(**kwargs):
            yield
    finally:
        _log_context.reset(token)


def get_log_context() -> Dict[str, Any]:
    """Get current merged log context."""
    return _log_context.get().copy()


def set_log_context(context: Dict[str, Any]) -> None:
    """Set current context directly (used by task boundary restore)."""
    _log_context.set(context)


class ContextPropagatingTask(Task):
    """
    Custom Celery task base class that applies explicit log context across
    Celery serialization boundary.

    Usage:
        @celery_app.task(base=ContextPropagatingTask, bind=True)
        def process_job_task(self, job_id: str):
            with logger.contextualize(task_id=self.request.id, job_id=job_id):
                logger.info("Task started")

    This ensures request_id flows from API → Worker → Webhook.
    """

    @staticmethod
    def sanitize_log_context(context: Dict[str, Any] | None) -> Dict[str, Any]:
        """Keep only non-null fields for task log context payload."""
        if not context:
            return {}
        return {k: v for k, v in context.items() if v is not None}

    def get_current_log_context(self) -> Dict[str, Any]:
        """Get context restored for the current task execution."""
        return get_log_context()

    def get_context_from_kwargs(self, kwargs: Dict[str, Any] | None) -> Dict[str, Any]:
        """Extract context payload from task kwargs if present."""
        if not kwargs:
            return {}
        context = kwargs.get(LOG_CONTEXT_KEY)
        if not isinstance(context, dict):
            return {}
        return self.sanitize_log_context(context)

    def apply_async(
        self,
        args=None,
        kwargs=None,
        task_id=None,
        producer=None,
        link=None,
        link_error=None,
        shadow=None,
        **options
    ):
        """Capture global context unless explicit context payload is provided."""
        kwargs = kwargs or {}
        explicit = kwargs.get(LOG_CONTEXT_KEY)
        if explicit is None:
            kwargs[LOG_CONTEXT_KEY] = self.sanitize_log_context(get_log_context())
        else:
            kwargs[LOG_CONTEXT_KEY] = self.sanitize_log_context(explicit)
        return super().apply_async(
            args=args,
            kwargs=kwargs,
            task_id=task_id,
            producer=producer,
            link=link,
            link_error=link_error,
            shadow=shadow,
            **options
        )

    def __call__(self, *args, **kwargs):
        """Restore explicit context payload and apply Loguru contextualize()."""
        context = self.get_context_from_kwargs(kwargs)
        kwargs.pop(LOG_CONTEXT_KEY, None)
        token = _log_context.set(context)
        try:
            with logger.contextualize(**context):
                return super().__call__(*args, **kwargs)
        finally:
            _log_context.reset(token)


def setup_logging(
    service_name: str
):
    """
    Setup structured logging with optional Logfire integration.

    This function configures:
    - Human-readable text logging to stdout
    - Base schema fields for all logs
    - Optional Logfire structured telemetry
    - Log level filtering

    Args:
        service_name: Must be "knowhere-api" or "knowhere-worker"
        component: Must be "api" or "worker"
        app: FastAPI app instance (optional, for FastAPI instrumentation)

    Raises:
        ValueError: If service_name is not recognized

    Usage:
        # API startup (apps/api/main.py)
        setup_logging(service_name="knowhere-api")
        app = FastAPI(...)
        # Then instrument FastAPI separately if needed

        # Worker startup (apps/worker/worker.py)
        from celery.signals import worker_init

        @worker_init.connect()
        def init_worker(*args, **kwargs):
            setup_logging(service_name="knowhere-worker")
    """
    # Import settings here to avoid circular imports
    from shared.core.config import settings

    # Validate service_name
    if service_name not in ["knowhere-api", "knowhere-worker"]:
        raise ValueError(
            f"Invalid service_name: {service_name}. "
            "Must be 'knowhere-api' or 'knowhere-worker'"
        )

    # Remove all existing handlers
    logger.remove()

    # Set base context BEFORE any log emission so every line has base fields
    logger.configure(extra={
        "schema_version": "1.0",
        "environment": settings.ENVIRONMENT,
        "event": LogEvent.APP_LOG.value,
    })

    # Console handler - respects LOG_LEVEL
    log_level = settings.LOG_LEVEL

    logger.add(
        sys.stdout,
        level=log_level,
        enqueue=True,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | "
            "{extra[event]} | {message}"
        ),
    )

    # Logfire integration
    if settings.LOGFIRE_TOKEN:
        try:
            import logfire

            logfire.configure(
                service_name=service_name,
                token=settings.LOGFIRE_TOKEN,
                console=False,
            )

            # Logfire sink: keep structured fields from bind()/contextualize().
            logger.add(
                **logfire.loguru_handler(),
                level="INFO",
            )

            # Instrument based on service type
            if service_name == "knowhere-api":
                logfire.instrument_celery()  # Required for trace propagation (enqueue side)
                logfire.instrument_httpx()  # Instrument HTTP client calls

                # Instrument database
                from shared.core.database import engine
                logfire.instrument_sqlalchemy(engine=engine)

                # Redis instrumentation disabled to reduce production noise/cost.

            elif service_name == "knowhere-worker":
                logfire.instrument_celery()  # Consumer side
                logfire.instrument_httpx()  # Instrument HTTP client calls in worker

                # Instrument database
                from shared.core.database import engine
                logfire.instrument_sqlalchemy(engine=engine)

                # Redis instrumentation disabled to reduce production noise/cost.

            logger.bind(event=LogEvent.LOGGING_CONFIGURED.value).info(
                f"Logfire integration enabled for {service_name}"
            )
        except ImportError:
            logger.bind(event=LogEvent.LOGGING_CONFIGURED.value).warning(
                "Logfire integration requested but logfire package not installed"
            )

    # Configure standard logging library to use loguru
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    _configure_noisy_third_party_loggers()

    logger.bind(event=LogEvent.LOGGING_CONFIGURED.value).info(
        f"Logging configured for {service_name} (level={log_level})"
    )


def _configure_noisy_third_party_loggers() -> None:
    """Reduce high-volume debug noise from third-party libraries."""
    noisy_logger_names = (
        "urllib3",
        "httpcore",
        "httpx",
        "aio_pika",
        "aiormq",
        "sqlalchemy.engine",
        "sqlalchemy.pool",
    )
    for logger_name in noisy_logger_names:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists.
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message.
        frame, depth = logging.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())
