from io import StringIO

from fastapi import HTTPException
from loguru import logger

from shared.core.exceptions.domain_exceptions import RateLimitException, UnknownException
from shared.core.logging import (
    _DEFAULT_CONSOLE_FORMAT,
    _DEVELOPMENT_CONSOLE_FORMAT,
    _downgrade_expected_logfire_exception,
)


class FakeExceptionHelper:
    def __init__(self, exception: BaseException) -> None:
        self.exception: BaseException = exception
        self.level: str = "error"
        self.no_record_exception_called: bool = False

    def no_record_exception(self) -> None:
        self.no_record_exception_called = True


def test_default_console_format_omits_extra_output():
    stream = StringIO()
    logger.remove()
    handler_id = logger.add(stream, format=_DEFAULT_CONSOLE_FORMAT)

    try:
        logger.bind(event="worker.task.start", task_id="task-123").info("Task started")
    finally:
        logger.remove(handler_id)

    output = stream.getvalue()

    assert "Task started" in output
    assert "worker.task.start" in output
    assert "task-123" not in output


def test_development_console_format_includes_extra_output():
    stream = StringIO()
    logger.remove()
    handler_id = logger.add(stream, format=_DEVELOPMENT_CONSOLE_FORMAT)

    try:
        logger.bind(event="worker.task.start", task_id="task-123").info("Task started")
    finally:
        logger.remove(handler_id)

    output = stream.getvalue()

    assert "Task started" in output
    assert "worker.task.start" in output
    assert "'task_id': 'task-123'" in output


def test_downgrade_expected_logfire_exception_marks_4xx_as_warning() -> None:
    helper = FakeExceptionHelper(
        RateLimitException(retry_after=15, limit=2, period="minute")
    )

    _downgrade_expected_logfire_exception(helper)

    assert helper.level == "warning"
    assert helper.no_record_exception_called is True


def test_downgrade_expected_logfire_exception_handles_fastapi_http_errors() -> None:
    helper = FakeExceptionHelper(
        HTTPException(status_code=404, detail="Resource not found")
    )

    _downgrade_expected_logfire_exception(helper)

    assert helper.level == "warning"
    assert helper.no_record_exception_called is True


def test_downgrade_expected_logfire_exception_preserves_5xx_errors() -> None:
    helper = FakeExceptionHelper(
        UnknownException(original_exception=RuntimeError("boom"))
    )

    _downgrade_expected_logfire_exception(helper)

    assert helper.level == "error"
    assert helper.no_record_exception_called is False
