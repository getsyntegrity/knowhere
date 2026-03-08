from io import StringIO

from loguru import logger

from shared.core.logging import _DEFAULT_CONSOLE_FORMAT, _DEVELOPMENT_CONSOLE_FORMAT


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
