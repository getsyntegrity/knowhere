import importlib
import os
import time
import requests
from typing import Any, Callable, Optional, cast
from shared.core.exceptions.domain_exceptions import (
    PDFParsingException,
    MinerUServiceException,
    TimeoutException,
    StorageServiceException,
    UnavailableException,
)
from shared.core.exceptions.knowhere_exception import KnowhereException

from loguru import logger

from shared.core.config import settings
from shared.core.constants import APIConstants
from app.services.document_parser.md_parser import parse_md
from app.services.document_parser.mineru_quota_manager import get_mineru_quota_manager
from shared.utils.FileDownUpUtils import s3_download_extract_zip
from shared.utils.CommonHelperSync import is_remote

MINERU_API_TIMEOUT = 60       # For API calls (get status, etc.)
MINERU_UPLOAD_TIMEOUT = 600   # For large file uploads (10 min max)


def get_mineru_headers(api_key: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def _get_retry_after_seconds(response: requests.Response, default_retry_after: int) -> int:
    """Parse Retry-After header with sane bounds for worker backoff."""
    retry_after_header = response.headers.get("Retry-After")
    if retry_after_header:
        try:
            return max(1, min(int(retry_after_header), MINERU_RATE_LIMIT_MAX_RETRY_AFTER))
        except ValueError:
            logger.debug(f"Invalid MinerU Retry-After header: {retry_after_header}")

    return max(1, min(default_retry_after, MINERU_RATE_LIMIT_MAX_RETRY_AFTER))


MINERU_RATE_LIMIT_DEFAULT_RETRY_AFTER = 15
MINERU_RATE_LIMIT_MAX_RETRY_AFTER = 60


def _mineru_logger(step: str, **fields):
    return logger.bind(service="mineru", step=step, **fields)


def _raise_mineru_unavailable(token_id: str, response: requests.Response, operation: str) -> None:
    retry_after = _get_retry_after_seconds(response, settings.MINERU_TOKEN_COOLDOWN_SECONDS)
    quota_manager = get_mineru_quota_manager()
    quota_manager.mark_rate_limited(token_id, retry_after)
    _mineru_logger(
        "rate_limited",
        operation=operation,
        token_id=token_id,
        status_code=response.status_code,
        retry_after=retry_after,
    ).warning("MinerU request rate-limited")
    raise UnavailableException(
        internal_message=f"MinerU rate limited during {operation}",
        retry_after=retry_after,
        limit=settings.MINERU_TOKEN_RPM_LIMIT,
        period="minute",
        user_message="MinerU is busy right now. Please retry shortly.",
    )


def poll_mineru_task(
    status_url: str,
    task_id: str,
    output_dir: str,
    get_status: Callable[[dict], Optional[dict]],
    preferred_token_id: Optional[str] = None,
) -> None:
    # Optimize polling strategy: add delay, timeout and error handling
    quota_manager = get_mineru_quota_manager()
    polling_logger = _mineru_logger(
        "poll_status",
        operation="poll_status",
        task_id=task_id,
        preferred_token_id=preferred_token_id,
    )

    max_polling_attempts = 120  # Max polling attempts (10 minutes)
    polling_interval = 5.0  # Polling interval (seconds)
    max_wait_time = 600  # Max wait time (10 minutes)

    # Dynamic polling interval: adjust based on task state
    def get_polling_interval(state: str, attempt: int) -> float:
        if state == "pending":
            return min(10.0, 2.0 + attempt * 0.5)  # Increase interval gradually while pending
        elif state == "running":
            return 5.0  # Keep 5s interval while running
        else:
            return 2.0  # Quick check for other states

    start_time = time.time()
    attempt = 0
    last_token_id: Optional[str] = None
    last_state: Optional[str] = None

    polling_logger.info("Starting MinerU polling")

    while attempt < max_polling_attempts:
        # Check for timeout
        if time.time() - start_time > max_wait_time:
            polling_logger.bind(
                attempt=attempt + 1,
                max_polling_attempts=max_polling_attempts,
                max_wait_time=max_wait_time,
            ).warning("MinerU polling timed out")
            raise TimeoutException(
                internal_message=f"PDF parsing timed out, exceeded {max_wait_time} seconds",
                retry_after=60,
                user_message="PDF parsing timed out. Please try again."
            )

        try:
            logger.debug(
                f"parse_pdfs status_url: {status_url} (attempt {attempt + 1}/{max_polling_attempts})"
            )
            lease = quota_manager.acquire_request(
                operation="poll_status",
                preferred_token_id=preferred_token_id,
            )
            if lease.token_id != last_token_id:
                polling_logger.bind(
                    token_id=lease.token_id,
                    attempt=attempt + 1,
                ).info("Acquired MinerU token for polling")
                last_token_id = lease.token_id
            status_header = get_mineru_headers(lease.api_key)
            res = requests.get(status_url, headers=status_header, timeout=MINERU_API_TIMEOUT)

            if res.status_code == 429:
                _raise_mineru_unavailable(lease.token_id, res, operation="poll_status")

            if res.status_code == 200:
                response_json = res.json()
                if response_json.get("code") != 0:
                    response_message = str(response_json.get("msg") or "Unknown error")
                    if "rate limit" in response_message.lower():
                        quota_manager.mark_rate_limited(
                            lease.token_id,
                            settings.MINERU_TOKEN_COOLDOWN_SECONDS,
                        )
                        raise UnavailableException(
                            internal_message=f"MinerU rate limited during poll_status: {response_message}",
                            retry_after=settings.MINERU_TOKEN_COOLDOWN_SECONDS,
                            limit=lease.rpm_limit,
                            period="minute",
                            user_message="MinerU is busy right now. Please retry shortly.",
                        )
                    raise MinerUServiceException(
                        internal_message=f"MinerU API Error: {response_message}"
                    )
                
                status = get_status(response_json)
                if not status:
                    polling_logger.bind(
                        token_id=lease.token_id,
                        attempt=attempt + 1,
                    ).warning("Received empty MinerU status payload")
                    time.sleep(polling_interval)
                    attempt += 1
                    continue

                state = status.get("state", "unknown")
                if state != last_state:
                    polling_logger.bind(
                        token_id=lease.token_id,
                        attempt=attempt + 1,
                        state=state,
                    ).info("MinerU status changed")
                    last_state = state

                if state == "done":
                    # Parsing completed
                    res_zip_url = status["full_zip_url"]
                    s3_download_extract_zip(
                        res_zip_url,
                        dest_dir=output_dir,
                        keep_exts=(".md", ".jpg", ".jpeg", ".png", ".gif", ".json"),
                        exclude_patterns=("content_list", "middle.json", "model.json"),  # Only keep layout.json
                    )
                    polling_logger.bind(token_id=lease.token_id).info("MinerU parsing completed")
                    break

                elif state == "running":
                    # Display progress
                    if "extract_progress" in status:
                        try:
                            progress = (
                                status["extract_progress"]["extracted_pages"]
                                / status["extract_progress"]["total_pages"]
                            )
                            polling_logger.bind(
                                token_id=lease.token_id,
                                progress=progress,
                            ).info("MinerU parsing progress updated")
                        except (KeyError, ZeroDivisionError):
                             polling_logger.bind(token_id=lease.token_id).info("MinerU parsing in progress")
                    else:
                        polling_logger.bind(token_id=lease.token_id).info("MinerU parsing in progress")

                elif state == "failed":
                    # 解析失败
                    error_msg = status.get("err_msg", "Unknown error")
                    polling_logger.bind(
                        token_id=lease.token_id,
                        error_message=error_msg,
                    ).error("MinerU parsing reported failed state")
                    raise PDFParsingException(
                        user_message=error_msg or "Failed to parse PDF file",
                        internal_message=f"MinerU failed with state 'failed': {error_msg}"
                    )

                elif state == "pending":
                    # Pending
                    polling_logger.bind(token_id=lease.token_id).debug("MinerU parsing pending")

                elif state == "waiting-file":
                    # Waiting for file upload queuing
                    polling_logger.bind(token_id=lease.token_id).debug("MinerU waiting for file queueing")
                
                elif state == "converting":
                    # Converting format
                    polling_logger.bind(token_id=lease.token_id).debug("MinerU converting file")

                else:
                    polling_logger.bind(
                        token_id=lease.token_id,
                        state=state,
                    ).warning("MinerU returned unknown state")

                # 动态调整轮询间隔
                current_interval = get_polling_interval(state, attempt)
                time.sleep(current_interval)
                attempt += 1

            else:
                polling_logger.bind(
                    token_id=lease.token_id,
                    attempt=attempt + 1,
                    status_code=res.status_code,
                ).warning("MinerU status query failed")
                time.sleep(polling_interval * 2)  # Extend wait on failure
                attempt += 1

        except requests.RequestException as e:
            polling_logger.bind(
                attempt=attempt + 1,
                error_message=str(e),
            ).warning("MinerU polling network request failed")
            time.sleep(polling_interval * 2)
            attempt += 1
        except KnowhereException:
            raise
        except Exception as e:
            polling_logger.bind(
                attempt=attempt + 1,
                error_message=str(e),
            ).error("Unexpected error during MinerU polling")
            raise PDFParsingException(
                user_message="An unexpected error occurred while parsing the PDF",
                internal_message=str(e),
                original_exception=e
            )

    if attempt >= max_polling_attempts:
        raise TimeoutException(
            internal_message=f"minerU PDF parsing timed out after {max_polling_attempts} attempts, Task ID: {task_id}",
            retry_after=60,
            user_message="PDF parsing timed out. Please try again."
        )


def upload_and_parse(pdf_url: str, filename: str, output_dir: str) -> None:
    base_url = settings.MINERU_URL
    quota_manager = get_mineru_quota_manager()
    source_kind = "remote_url" if is_remote(pdf_url) else "local_file"
    upload_logger = _mineru_logger(
        "upload_url",
        operation="upload_url",
        filename=filename,
        source_kind=source_kind,
    )

    url = f"{base_url}/file-urls/batch"
    payload = {
        "files": [{"name": filename}],
        "enable_formula": True,
        "enable_table": True,
        "language": "auto",
        "model_version": "vlm"
    }

    upload_logger.info("Requesting MinerU upload URL")
    lease = quota_manager.acquire_request(operation="upload_url")
    upload_logger.bind(token_id=lease.token_id).info("Acquired MinerU token for upload URL")
    headers = get_mineru_headers(lease.api_key)
    res = requests.post(url, headers=headers, json=payload, timeout=MINERU_API_TIMEOUT)
    if res.status_code == 429:
        _raise_mineru_unavailable(lease.token_id, res, operation="upload_url")
    if res.status_code != 200:
        upload_logger.bind(
            token_id=lease.token_id,
            status_code=res.status_code,
        ).error("Failed to get MinerU upload URL")
        raise MinerUServiceException(
            internal_message=f"Failed to get upload URL: {res.text}",
            status_code=res.status_code
        )

    result = res.json()
    if result.get("code") != 0:
        response_message = str(result.get("msg", "Unknown error"))
        if "rate limit" in response_message.lower():
            quota_manager.mark_rate_limited(
                lease.token_id,
                settings.MINERU_TOKEN_COOLDOWN_SECONDS,
            )
            upload_logger.bind(
                token_id=lease.token_id,
                retry_after=settings.MINERU_TOKEN_COOLDOWN_SECONDS,
                error_message=response_message,
            ).warning("MinerU upload URL request hit rate limit")
            raise UnavailableException(
                internal_message=f"MinerU rate limited during upload_url: {response_message}",
                retry_after=settings.MINERU_TOKEN_COOLDOWN_SECONDS,
                limit=lease.rpm_limit,
                period="minute",
                user_message="MinerU is busy right now. Please retry shortly.",
            )
        upload_logger.bind(
            token_id=lease.token_id,
            error_message=response_message,
        ).error("MinerU upload URL request returned API error")
        raise MinerUServiceException(
            internal_message=f"MinerU API error: {response_message}"
        )

    batch_id = result["data"]["batch_id"]
    upload_url = result["data"]["file_urls"][0]
    upload_logger = upload_logger.bind(token_id=lease.token_id, batch_id=batch_id)
    upload_logger.info("Received MinerU upload URL")

    upload_logger.info("Starting MinerU file transfer")
    
    # Support both local files and remote URLs
    if is_remote(pdf_url):
        # Remote URL: download to temp file first, then upload
        import tempfile
        upload_logger.info("Downloading remote source file before MinerU upload")
        try:
            download_res = requests.get(pdf_url, stream=True, timeout=APIConstants.S3_FILE_DOWNLOAD_TIMEOUT)
            download_res.raise_for_status()
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp_file:
                for chunk in download_res.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                tmp_path = tmp_file.name
            
            upload_logger.bind(temp_file_path=tmp_path).info("Uploading staged file to MinerU")
            with open(tmp_path, "rb") as f:
                upload_res = requests.put(
                    upload_url, 
                    data=f, 
                    timeout=MINERU_UPLOAD_TIMEOUT
                )
            
            # Clean up temp file
            os.unlink(tmp_path)
            
        except requests.RequestException as e:
            upload_logger.bind(error_message=str(e)).error("Failed to stage remote source file for MinerU")
            raise StorageServiceException(
                internal_message=f"Failed to download remote file: {e}"
            )
    else:
        # Local file: upload directly
        upload_logger.bind(local_path=pdf_url).info("Uploading local file to MinerU")
        try:
            with open(pdf_url, "rb") as f:
                upload_res = requests.put(
                    upload_url, 
                    data=f, 
                    timeout=MINERU_UPLOAD_TIMEOUT
                )
        except IOError as e:
            upload_logger.bind(error_message=str(e)).error("Failed to read local file for MinerU upload")
            raise StorageServiceException(
                internal_message=f"Failed to read local file: {e}"
            )
    
    if upload_res.status_code != 200:
        upload_logger.bind(status_code=upload_res.status_code).error("MinerU file upload failed")
        raise MinerUServiceException(
            internal_message=f"Failed to upload file to MinerU: {upload_res.text}",
            status_code=upload_res.status_code
        )

    upload_logger.info("MinerU file upload completed, switching to polling")

    status_url = f"{base_url}/extract-results/batch/{batch_id}"

    def get_batch_status(data: dict) -> Optional[dict]:
        extract_result = data.get("data", {}).get("extract_result")
        if isinstance(extract_result, list):
            return extract_result[0] if extract_result else None
        return extract_result

    poll_mineru_task(
        status_url=status_url,
        task_id=batch_id,
        output_dir=output_dir,
        get_status=get_batch_status,
        preferred_token_id=lease.token_id,
    )


def parse_pdfs(pdf_path, filename, output_dir, base_llm_paras, profile=None, relative_root=None):
    route = profile.route if profile else "standard"
    
    if route == "fast":
        # Fast path: use pymupdf4llm for local PDF conversion (no MinerU API call)
        # Handles text, tables, and images — outputs GitHub-compatible markdown
        logger.info(f"⚡ Fast path: extracting with pymupdf4llm for {filename}")
        pymupdf4llm = cast(Any, importlib.import_module("pymupdf4llm"))
        
        os.makedirs(output_dir, exist_ok=True)
        image_dir = os.path.join(output_dir, "images")
        os.makedirs(image_dir, exist_ok=True)
        
        md_text = pymupdf4llm.to_markdown(
            pdf_path,
            write_images=True,
            image_path=image_dir,
            image_format="png",
        )
        
        # Write full.md for downstream compatibility
        full_md_path = os.path.join(output_dir, "full.md")
        with open(full_md_path, "w", encoding="utf-8") as f:
            f.write(md_text)
        
        img_count = len([f for f in os.listdir(image_dir) if f.endswith(".png")])
        logger.info(f"⚡ Fast path: wrote {len(md_text)} chars to full.md, {img_count} images extracted")
    else:
        # Standard path: MinerU VLM API
        upload_and_parse(pdf_path, filename, output_dir)

    logger.info("✅ PDF parsing step 1 complete: text extracted")

    base_llm_paras.update({"doc_name": filename})
    parsed_df = parse_md(output_dir, source_type='md', file_path=os.path.join(output_dir, 'full.md'), base_llm_paras=base_llm_paras, relative_root=relative_root)
    return parsed_df
