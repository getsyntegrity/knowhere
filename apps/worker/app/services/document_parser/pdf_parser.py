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
    # 优化轮询策略：添加延迟、超时和错误处理
    status_header = get_mineru_headers()

    max_polling_attempts = 120  # 最大轮询次数 (10分钟)
    polling_interval = 5.0  # 轮询间隔(秒)
    max_wait_time = 600  # 最大等待时间(10分钟)

    # 动态轮询间隔：根据任务状态调整
    def get_polling_interval(state: str, attempt: int) -> float:
        if state == "pending":
            return min(10.0, 2.0 + attempt * 0.5)  # 等待中逐渐增加间隔
        elif state == "running":
            return 5.0  # 运行中保持5秒间隔
        else:
            return 2.0  # 其他状态快速检查

    start_time = time.time()
    attempt = 0

    while attempt < max_polling_attempts:
        # 检查是否超时
        if time.time() - start_time > max_wait_time:
            raise TimeoutError(f"PDF解析超时，等待时间超过{max_wait_time}秒")

        try:
            logger.debug(
                f"parse_pdfs status_url: {status_url} (尝试 {attempt + 1}/{max_polling_attempts})"
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
                    # 解析完成
                    res_zip_url = status["full_zip_url"]
                    s3_download_extract_zip(
                        res_zip_url,
                        dest_dir=output_dir,
                        keep_exts=[".md", ".jpg", ".jpeg", ".png", ".gif"],
                    )
                    logger.info(f"PDF解析完成，任务ID: {task_id}")
                    break

                elif state == "running":
                    # 显示进度
                    if "extract_progress" in status:
                        try:
                            progress = (
                                status["extract_progress"]["extracted_pages"]
                                / status["extract_progress"]["total_pages"]
                            )
                            logger.info(f"PDF解析进度: {progress:.2%} (任务ID: {task_id})")
                        except (KeyError, ZeroDivisionError):
                             logger.info(f"PDF解析进行中... (任务ID: {task_id})")
                    else:
                        logger.info(f"PDF解析进行中... (任务ID: {task_id})")

                elif state == "failed":
                    # 解析失败
                    error_msg = status.get("err_msg", "未知错误")
                    raise Exception(f"PDF解析失败: {error_msg}")

                elif state == "pending":
                    # 排队中
                    logger.debug(f"PDF解析排队中... (任务ID: {task_id})")

                elif state == "waiting-file":
                    # 等待文件上传排队
                    logger.debug(f"PDF解析等待文件上传排队... (任务ID: {task_id})")
                
                elif state == "converting":
                    # 格式转换中
                    logger.debug(f"PDF解析格式转换中... (任务ID: {task_id})")

                else:
                    logger.warning(f"Unknown state: {state}, full response: {status}")

                # 动态调整轮询间隔
                current_interval = get_polling_interval(state, attempt)
                await asyncio.sleep(current_interval)
                attempt += 1

            else:
                logger.warning(f"状态查询失败，状态码: {res.status_code}")
                await asyncio.sleep(polling_interval * 2)  # 失败时延长等待
                attempt += 1

        except requests.RequestException as e:
            logger.warning(f"网络请求失败: {e}")
            await asyncio.sleep(polling_interval * 2)
            attempt += 1
        except Exception as e:
            logger.error(f"PDF解析过程中出错: {e}")
            raise

    if attempt >= max_polling_attempts:
        raise TimeoutError(
            f"PDF解析超时，已轮询{max_polling_attempts}次，任务ID: {task_id}"
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
        raise Exception(f"Failed to get upload URL: {res.status_code} - {res.text}")

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
                f"Failed to upload file: {upload_res.status_code} - {upload_res.text}"
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
                raise Exception(f"Failed to submit task: {res.status_code} - {res.text}")

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

    logger.info("✅ 解析PDF第一步完成 已解压为md存储")

    base_llm_paras.update({"doc_name": filename})
    await parse_md(
        output_dir,
        source_type="md",
        file_path=os.path.join(output_dir, "full.md"),
        base_llm_paras=base_llm_paras,
    )
    logger.info("✅ 解析PDF第二步完成 已通过md_parser获取知识数据")
