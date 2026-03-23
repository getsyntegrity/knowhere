import pytest

from app.services.messaging.message_consumer import MessageConsumer
from shared.core.exceptions.domain_exceptions import WorkerHandlingException


@pytest.mark.asyncio
async def test_process_message_drops_non_retryable_handler_result():
    consumer = MessageConsumer()

    async def handler(message_data):
        return {"status": "failed", "retryable": False, "reason": "invalid_transition"}

    message = type("IncomingMessageStub", (), {"body": b'{"job_id": "job_123"}'})()

    await consumer._process_message(message, handler, "job_result")


@pytest.mark.asyncio
async def test_process_message_raises_for_retryable_handler_result():
    consumer = MessageConsumer()

    async def handler(message_data):
        return {"status": "failed", "reason": "transient_failure"}

    message = type("IncomingMessageStub", (), {"body": b'{"job_id": "job_123"}'})()

    with pytest.raises(WorkerHandlingException):
        await consumer._process_message(message, handler, "job_result")
