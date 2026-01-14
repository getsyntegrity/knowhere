import os
import time
import asyncio
import requests
from typing import Callable, Optional

from loguru import logger

from shared.core.config import settings
from shared.utils.env import is_development
from shared.core.constants import APIConstants
from app.services.document_parser.md_parser import parse_md
from shared.utils.FileDownUpUtils import s3_download_extract_zip

MINERU_API_TIMEOUT = 60

def get_mineru_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.MINERU_API_KEY}",
    }


async def poll_mineru_task(
    status_url: str,
    task_id: str,
    output_dir: str,
    get_status: Callable[[dict], Optional[dict]],
) -> None:
    # Optimize polling strategy: add delay, timeout and error handling
    status_header = get_mineru_headers()

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

    while attempt < max_polling_attempts:
        # Check for timeout
        if time.time() - start_time > max_wait_time:
            raise TimeoutError(f"PDF parsing timed out, exceeded {max_wait_time} seconds")

        try:
            logger.debug(
                f"parse_pdfs status_url: {status_url} (attempt {attempt + 1}/{max_polling_attempts})"
            )
            res = requests.get(status_url, headers=status_header, timeout=MINERU_API_TIMEOUT)

            if res.status_code == 200:
                response_json = res.json()
                if response_json.get("code") != 0:
                     raise Exception(f"MinerU API Error: {response_json.get('msg')}")
                
                status = get_status(response_json)
                if not status:
                    logger.warning(f"Empty data received from MinerU: {response_json}")
                    await asyncio.sleep(polling_interval)
                    attempt += 1
                    continue

                state = status.get("state", "unknown")

                if state == "done":
                    # Parsing completed
                    res_zip_url = status["full_zip_url"]
                    s3_download_extract_zip(
                        res_zip_url,
                        dest_dir=output_dir,
                        keep_exts=[".md", ".jpg", ".jpeg", ".png", ".gif"],
                    )
                    logger.info(f"PDF parsing completed, Task ID: {task_id}")
                    break

                elif state == "running":
                    # Display progress
                    if "extract_progress" in status:
                        try:
                            progress = (
                                status["extract_progress"]["extracted_pages"]
                                / status["extract_progress"]["total_pages"]
                            )
                            logger.info(f"PDF parsing progress: {progress:.2%} (Task ID: {task_id})")
                        except (KeyError, ZeroDivisionError):
                             logger.info(f"PDF parsing in progress... (Task ID: {task_id})")
                    else:
                        logger.info(f"PDF parsing in progress... (Task ID: {task_id})")

                elif state == "failed":
                    # Parsing failed
                    error_msg = status.get("err_msg", "Unknown error")
                    raise Exception(f"MinerU PDF parsing failed: {error_msg}")

                elif state == "pending":
                    # Pending
                    logger.debug(f"PDF parsing pending... (Task ID: {task_id})")

                elif state == "waiting-file":
                    # Waiting for file upload queuing
                    logger.debug(f"PDF parsing waiting for file upload queuing... (Task ID: {task_id})")
                
                elif state == "converting":
                    # Converting format
                    logger.debug(f"PDF parsing converting format... (Task ID: {task_id})")

                else:
                    logger.warning(f"Unknown state: {state}, full response: {status}")

                # 动态调整轮询间隔
                current_interval = get_polling_interval(state, attempt)
                await asyncio.sleep(current_interval)
                attempt += 1

            else:
                logger.warning(f"Status query failed, status code: {res.status_code}")
                await asyncio.sleep(polling_interval * 2)  # Extend wait on failure
                attempt += 1

        except requests.RequestException as e:
            logger.warning(f"Network request failed: {e}")
            await asyncio.sleep(polling_interval * 2)
            attempt += 1
        except Exception as e:
            logger.error(f"Error during PDF parsing: {e}")
            raise

    if attempt >= max_polling_attempts:
        raise TimeoutError(
            f"minerU PDF parsing timed out after {max_polling_attempts} attempts, Task ID: {task_id}"
        )


async def upload_and_parse(pdf_url: str, filename: str, output_dir: str) -> None:
    base_url = settings.MINERU_URL
    headers = get_mineru_headers()

    url = f"{base_url}/file-urls/batch"
    payload = {
        "files": [{"name": filename}],
        "enable_formula": True,
        "enable_table": True,
        "language": "auto",
    }

    logger.info(f"Requesting upload URL for: {filename}")
    res = requests.post(url, headers=headers, json=payload, timeout=MINERU_API_TIMEOUT)
    if res.status_code != 200:
        raise Exception(f"MinerU Failed to get upload URL: {res.status_code} - {res.text}")

    result = res.json()
    if result.get("code") != 0:
        raise Exception(f"MinerU API error: {result.get('msg', 'Unknown error')}")

    batch_id = result["data"]["batch_id"]
    upload_url = result["data"]["file_urls"][0]
    logger.info(f"Got batch_id: {batch_id}")

    logger.info(f"Streaming file from {pdf_url} to MinerU...")
    with requests.get(
        pdf_url, stream=True, timeout=APIConstants.S3_FILE_DOWNLOAD_TIMEOUT
    ) as download_response:
        download_response.raise_for_status()
        upload_res = requests.put(
            upload_url,
            data=download_response.iter_content(chunk_size=8192),
            timeout=MINERU_API_TIMEOUT,
        )
        if upload_res.status_code != 200:
            raise Exception(
                f"MinerU Failed to upload file: {upload_res.status_code} - {upload_res.text}"
            )

    logger.info("File uploaded successfully, waiting for parsing...")

    status_url = f"{base_url}/extract-results/batch/{batch_id}"

    def get_batch_status(data: dict) -> Optional[dict]:
        extract_result = data.get("data", {}).get("extract_result")
        if isinstance(extract_result, list):
            return extract_result[0] if extract_result else None
        return extract_result

    await poll_mineru_task(
        status_url=status_url,
        task_id=batch_id,
        output_dir=output_dir,
        get_status=get_batch_status,
    )


async def parse_pdfs(pdf_path, filename, output_dir, base_llm_paras, mode="api"):
    if mode == "api":
        if is_development():
            """
            on local development, we can not pass localStack presigned url to mineru api
            instead, we need to upload the file to mineru
            """
            await upload_and_parse(pdf_path, filename, output_dir)
        else:
            base_url = settings.MINERU_URL
            url = f"{base_url}/extract/task"
            headers = get_mineru_headers()

            payload = {
                "url": pdf_path,
                "is_ocr": True,
                "enable_formula": True,
                "language": "auto",
            }

            logger.info(f"🔗 Submitting task for: {filename}")

            res = requests.post(url, headers=headers, json=payload, timeout=MINERU_API_TIMEOUT)
            if res.status_code != 200:
                raise Exception(f"MinerU Failed to submit task to mineru api: {url}, {res.status_code} - {res.text}")

            result = res.json()
            if result.get("code") != 0:
                raise Exception(f"MinerU API error: {result.get('msg', 'Unknown error')}")

            task_id = result["data"]["task_id"]
            status_url = f"{base_url}/extract/task/{task_id}"
            logger.info(f"🔗 Task submitted, task_id: {task_id}")

            await poll_mineru_task(
                status_url=status_url,
                task_id=task_id,
                output_dir=output_dir,
                get_status=lambda d: d.get("data"),
            )
    else:
        raise ValueError(f"Unknown PDF parser mode: {mode}")

    logger.info("✅ PDF parsing step 1 complete: Unzipped and stored as md")

    base_llm_paras.update({"doc_name":filename})
    parsed_df = await parse_md(output_dir, source_type='md', file_path=os.path.join(output_dir, 'full.md'), base_llm_paras=base_llm_paras)
    print("✅ PDF parsing step 2 complete: Knowledge data retrieved via md_parser")
    return parsed_df
