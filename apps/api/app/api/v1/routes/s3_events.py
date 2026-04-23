"""
S3 event webhook routes.
"""
import base64
import json
import os
from typing import Any, Dict

import aiohttp
from shared.core.database import get_db_context
from shared.core.logging import LogEvent
from shared.core.state_machine.states import JobStatus
from shared.models.schemas.oss_event import OSSEvent
from shared.models.schemas.s3_event import S3Event
from app.repositories.job_repository import JobRepository
from app.services.knowledge.kb_orchestrator import KBOrchestrator
from app.services.state_machine import JobStateMachine
from fastapi import APIRouter, Header, Request
from loguru import logger

router = APIRouter(tags=["Internal"])


def verify_sns_signature(request_body: bytes, signature: str, message: str) -> bool:
    """
    Validate an SNS message signature.

    Args:
        request_body: Request body.
        signature: Signature header value.
        message: Message payload.

    Returns:
        bool: Whether validation succeeded.
    """
    try:
        # This is intentionally simplified. Production code should use the AWS SDK.
        return True
    except Exception as e:
        logger.error(f"SNS signature verification failed: {e}")
        return False


def verify_minio_signature(auth_token: str, expected_token: str) -> bool:
    """
    Validate the MinIO webhook token.

    Args:
        auth_token: Token supplied by the request.
        expected_token: Token configured on the server.

    Returns:
        bool: Whether validation succeeded.
    """
    if not expected_token:
        return True  # Skip verification when no token is configured.
    
    return auth_token == expected_token


def verify_oss_signature(request_body: bytes, headers: Dict[str, str]) -> bool:
    """
    Validate an OSS callback signature.

    Args:
        request_body: Request body.
        headers: Request headers.

    Returns:
        bool: Whether validation succeeded.
    """
    try:
        from shared.core.config import settings

        # Allow an opt-out for local development and controlled environments.
        if not getattr(settings, 'OSS_EVENT_VERIFY_SIGNATURE', True):
            return True
        
        # OSS callback verification is simplified here. Production code should
        # follow the official OSS callback verification flow.
        callback_key = getattr(settings, 'OSS_EVENT_CALLBACK_KEY', '')
        if not callback_key:
            logger.warning("OSS_EVENT_CALLBACK_KEY is not configured; skipping signature verification")
            return True
        
        # TODO: Implement OSS callback signature verification.
        # Expected steps:
        # 1. Read the signature metadata from the headers.
        # 2. Compute the signature with callback_key.
        # 3. Compare the computed and provided signatures.
        
        return True
    except Exception as e:
        logger.error(f"OSS signature verification failed: {e}")
        return False


def extract_job_id_from_s3_key(s3_key: str) -> str | None:
    """
    Extract the job_id from an S3 object key.

    Args:
        s3_key: S3 key in the format uploads/{job_id}.ext.

    Returns:
        str: Job identifier.
    """
    if not s3_key.startswith("uploads/"):
        return None
    
    # Strip the uploads/ prefix and remove the file extension.
    filename = s3_key[8:]  # Remove the "uploads/" prefix.
    job_id = os.path.splitext(filename)[0]
    
    return job_id


@router.get("/s3-events", response_model=dict, summary="Handle S3 webhook GET requests")
async def handle_s3_events_get(
    request: Request,
    x_amz_sns_message_type: str = Header(None, alias="x-amz-sns-message-type"),
    x_minio_auth_token: str = Header(None, alias="x-minio-auth-token"),
    authorization: str = Header(None)
):
    """
    Handle S3-event GET requests, primarily for SNS subscription confirmation.
    """
    logger.info("======== S3 event GET request ========")
    logger.info(f"Headers: {dict(request.headers)}")
    if request.client:
        logger.info(f"Client IP: {request.client.host}")

    # Handle SNS subscription confirmation requests.
    if x_amz_sns_message_type == "SubscriptionConfirmation":
        logger.info("Received an SNS subscription confirmation request")
        return {"message": "SNS subscription confirmed"}
    
    return {"message": "GET request handled"}


@router.post("/s3-events", response_model=dict, summary="Handle S3 webhook POST requests")
async def handle_s3_events(
    request: Request,
    x_amz_sns_message_type: str = Header(None, alias="x-amz-sns-message-type"),
    x_minio_auth_token: str = Header(None, alias="x-minio-auth-token"),
    authorization: str = Header(None)
):
    """
    Handle S3-event POST requests from AWS SNS, MinIO, or OSS.
    """
    logger.bind(event = LogEvent.S3_WEBHOOK_EVENT).info(f"S3 event Headers: {dict(request.headers)}")
    if request.client:
        logger.info(f"Client IP: {request.client.host}")
    try:
        # Read the request body.
        body = await request.body()
        headers = dict(request.headers)
        
        # Determine the event source.
        if x_amz_sns_message_type:
            # AWS SNS event.
            result = await handle_sns_event(body)
            if result:
                return result
        elif _is_oss_event(headers):
            # OSS event, including Aliyun MNS proxy notifications.
            await handle_oss_event(body, headers)
        elif x_minio_auth_token:
            # MinIO event, identified by the dedicated x-minio-auth-token header.
            await handle_minio_event(body, x_minio_auth_token)
        else:
            # Direct S3 event payload used in tests.
            await handle_direct_s3_event(body)
        
        return {"message": "Event handled successfully"}
        
    except Exception as e:
        logger.error(f"Failed to handle S3 event: {e}")
        # Return 200 even on failure so the upstream storage service does not retry blindly.
        return {"message": "Event handling completed"}


async def handle_sns_event(body: bytes):
    """
    Handle an AWS SNS event payload.
    """
    try:
        # Parse the SNS message envelope.
        sns_message = json.loads(body.decode('utf-8'))
        
        # Branch on the SNS message type.
        message_type = sns_message.get('Type')
        logger.info(f"SNS message type: {message_type}")
        
        if message_type == 'SubscriptionConfirmation':
            # Handle subscription confirmation.
            logger.info("Received an SNS subscription confirmation request")
            subscribe_url = sns_message.get('SubscribeURL')
            if subscribe_url:
                logger.info(f"SNS subscription confirmation URL: {subscribe_url}")
                # Visit the URL to confirm the subscription.
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(subscribe_url) as response:
                            if response.status == 200:
                                logger.info("SNS subscription confirmed successfully")
                                return {"message": "SNS subscription confirmed"}
                            else:
                                logger.error(f"SNS subscription confirmation failed, status={response.status}")
                                return {"message": "SNS subscription confirmation failed"}
                except Exception as e:
                    logger.error(f"Failed to reach the SNS confirmation URL: {e}")
                    return {"message": "SNS subscription confirmation failed"}
            else:
                logger.warning("SNS subscription confirmation did not include SubscribeURL")
                return {"message": "SNS subscription confirmation failed"}
        
        elif message_type == 'Notification':
            # Handle notification messages.
            logger.info("Received an SNS notification")
            logger.info(f"SNS message payload: {sns_message}")
            
            # Parse the embedded S3 event.
            try:
                s3_event_data = json.loads(sns_message['Message'])
                logger.info(f"S3 event payload: {s3_event_data}")
                
                # Skip S3 test events — AWS/LocalStack sends these when
                # bucket notification configuration is first applied.
                # They lack the standard Records[] structure.
                if isinstance(s3_event_data, dict) and s3_event_data.get('Event') == 's3:TestEvent':
                    logger.info("Skip S3 test event")
                    return {"message": "S3 test event confirmed and skipped"}
                
                s3_event = S3Event(**s3_event_data)
                
                # Process the upload events.
                await process_upload_events(s3_event)
            except Exception as e:
                logger.error(f"Failed to parse the S3 event payload: {e}")
                logger.error(f"SNS payload: {sns_message}")
                # Fall back to treating the SNS payload itself as an S3 event.
                try:
                    s3_event = S3Event(**sns_message)
                    await process_upload_events(s3_event)
                except Exception as e2:
                    logger.error(f"Fallback parsing of the SNS payload as an S3 event also failed: {e2}")
                    raise
        else:
            logger.warning(f"Unknown SNS message type: {message_type}")
            return {"message": f"Unknown SNS message type: {message_type}"}
        
    except Exception as e:
        logger.error(f"Failed to handle SNS event: {e}")
        raise


async def handle_minio_event(body: bytes, auth_token: str):
    """
    Handle a MinIO webhook event.
    """
    try:
        # Validate the webhook token.
        from shared.core.config import settings
        expected_token = getattr(settings, 'S3_WEBHOOK_AUTH_TOKEN', '')
        
        if not verify_minio_signature(auth_token, expected_token):
            logger.warning("MinIO webhook authentication failed")
            return
        
        # Parse the S3 event payload.
        s3_event_data = json.loads(body.decode('utf-8'))
        s3_event = S3Event(**s3_event_data)
        
        # Process the upload events.
        await process_upload_events(s3_event)
        
    except Exception as e:
        logger.error(f"Failed to handle MinIO event: {e}")


async def handle_direct_s3_event(body: bytes):
    """
    Handle a direct S3 event payload used in tests.
    """
    try:
        # Parse the S3 event payload.
        s3_event_data = json.loads(body.decode('utf-8'))
        s3_event = S3Event(**s3_event_data)
        
        # Process the upload events.
        await process_upload_events(s3_event)
        
    except Exception as e:
        logger.error(f"Failed to handle direct S3 event: {e}")


def _is_oss_event(headers: Dict[str, str]) -> bool:
    """
    Return whether the incoming request looks like an OSS event.

    Args:
        headers: Request headers.

    Returns:
        bool: Whether the request matches OSS event heuristics.
    """
    # Identify OSS events by storage type, known headers, or request shape.
    
    storage_type = os.getenv('S3_TYPE', 's3').lower()
    if storage_type == 'oss':
        return True
    
    # Also look for OSS-specific headers such as x-oss-pub-key-url.
    if 'x-oss-pub-key-url' in headers:
        return True
    
    # Recognize Aliyun MNS proxy headers and user agents.
    if 'x-mns-version' in headers or 'x-mns-signing-cert-url' in headers:
        return True
    user_agent = headers.get('user-agent') or headers.get('User-Agent')
    if user_agent and 'Aliyun Notification Service Agent' in user_agent:
        return True
    
    return False


async def handle_oss_event(body: bytes, headers: Dict[str, str]):
    """
    Handle an OSS event payload.
    """
    try:
        # Verify the callback signature.
        if not verify_oss_signature(body, headers):
            logger.warning("OSS event signature verification failed")
            return
        
        # Parse the OSS payload, including MNS wrapper envelopes.
        event_data = json.loads(body.decode('utf-8'))
        logger.info(f"OSS event payload: {event_data}")
        # MNS may place the real event inside Message as base64 or raw JSON.
        if isinstance(event_data, dict) and 'Message' in event_data:
            inner = event_data.get('Message')
            if isinstance(inner, str):
                decoded = None
                # Prefer base64 decoding first.
                try:
                    decoded_bytes = base64.b64decode(inner, validate=True)
                    decoded_str = decoded_bytes.decode('utf-8')
                    decoded = json.loads(decoded_str)
                except Exception:
                    decoded = None
                
                if decoded is None:
                    # Fall back to parsing the raw JSON string directly.
                    try:
                        decoded = json.loads(inner)
                    except Exception:
                        decoded = None
                
                if decoded is not None:
                    event_data = decoded
                    logger.info(f"Decoded MNS Message payload: {event_data}")
            elif isinstance(inner, dict):
                event_data = inner
        
        # Detect the payload shape.
        if 'events' in event_data:
            # Standard OSS event format.
            oss_event = OSSEvent(**event_data)
        elif 'Records' in event_data:
            # Compatibility path for S3-like payloads emitted by OSS.
            oss_event = _convert_s3_format_to_oss(event_data)
        else:
            logger.error(f"Unknown OSS event format: {event_data}")
            return
        
        # Convert to S3Event so the existing upload flow can be reused.
        s3_event = oss_event.to_s3_event()
        
        # Process the upload events.
        await process_upload_events(s3_event)
        
    except Exception as e:
        logger.error(f"Failed to handle OSS event: {e}")
        raise


def _convert_s3_format_to_oss(event_data: Dict[str, Any]) -> OSSEvent:
    """
    Convert an S3-style event payload into an OSS event payload.

    Args:
        event_data: S3-format event data.

    Returns:
        OSSEvent: OSS event object.
    """
    from shared.models.schemas.oss_event import OSSEventRecord

    # Convert each S3-style record into the OSS schema.
    records = event_data.get('Records', [])
    oss_records = []
    
    for record in records:
        oss_record = OSSEventRecord(
            eventName=record.get('eventName', '').replace('s3:', ''),
            eventSource='acs:oss',
            eventTime=record.get('eventTime', ''),
            region=record.get('awsRegion', ''),
            oss={
                'bucket': record.get('s3', {}).get('bucket', {}),
                'object': record.get('s3', {}).get('object', {})
            }
        )
        oss_records.append(oss_record)
    
    return OSSEvent(events=oss_records)


async def process_upload_events(s3_event: S3Event):
    """
    Process upload events delivered by S3-compatible storage.

    Args:
        s3_event: S3 event object.
    """
    try:
        # Gather only upload-related records.
        upload_events = s3_event.get_upload_events()

        # Instantiate services once outside the loop
        job_repo = JobRepository()

        for event in upload_events:
            # Read the object key from the event record.
            s3_key = event.object_key or event.s3.get('object', {}).get('key')
            if not s3_key:
                continue

            # Extract the job_id from the object key.
            job_id = extract_job_id_from_s3_key(s3_key)
            if not job_id:
                logger.warning(f"Could not extract job_id from S3 key: {s3_key}")
                continue

            logger.info(f"Processing S3 upload event: {s3_key} -> job_id={job_id}")

            # Load the matching job.
            async with get_db_context() as db:
                job = await job_repo.get_job_by_id(db, job_id)

                if not job:
                    logger.warning(f"No job found for upload event: {job_id}")
                    continue

                # Only react while the job is still waiting for file upload.
                if job.status != "waiting-file":
                    logger.info(f"Job {job_id} is not in waiting-file status: {job.status}")
                    continue

                # Check if upload window has expired (race-condition safe via optimistic lock)
                from shared.core.config import settings
                from shared.core.state_machine.states import is_job_expired
                if is_job_expired(job.updated_at, settings.JOB_WAITING_EXPIRE_SECONDS):
                    logger.warning(f"Job {job_id} upload expired, marking failed")
                    state_machine = JobStateMachine()
                    await state_machine.mark_failed(
                        db, job_id,
                        "Upload expired: file was not uploaded within the allowed time window",
                        error_code="UPLOAD_EXPIRED",
                    )
                    continue

                # Skip S3 file verification — we are processing the upload
                # notification itself, so the file is guaranteed to exist.

                # Advance the job state.
                state_machine = JobStateMachine()

                # Once upload is complete, move the job to pending.
                await state_machine.transition(
                    db, job_id, JobStatus.PENDING.value,
                    "s3_upload_completed", None, "system"
                )

                # Start job processing.
                if job.job_type == "kb_management":
                    orchestrator = KBOrchestrator()
                    await orchestrator.start_workflow(
                        db=db,
                        job_id=job_id,
                        source_type="file",
                        file_path=None,
                        file_url=None,
                        user_id=str(job.user_id)
                    )
                else:
                    logger.warning(f"Unsupported job type for upload event: {job.job_type}, job_id={job_id}")

                logger.info(f"Triggered processing for job {job_id}")

    except Exception as e:
        logger.error(f"Failed to process upload events: {e}")
        raise
