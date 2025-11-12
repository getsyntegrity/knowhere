import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置 PYTHONPATH 环境变量
os.environ["PYTHONPATH"] = str(project_root)

# 加载环境变量
from dotenv import load_dotenv

env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ 已加载环境变量文件: {env_path}")
else:
    print(f"⚠️ 未找到.env文件: {env_path}")

import requests
import asyncio
import uuid
import json
from loguru import logger
from typing import Optional, Dict
from app.core.database import get_db_context
from app.core.tasks.kb_tasks import (
    _parse_and_vectorize_async,
    _store_to_db_async,
    _send_webhook_async,
)
from app.repositories.job_repository import JobRepository
from app.services.storage.file_upload_service import FileUploadService
from app.services.user.user_config_service import UserConfigService


def upload_file_to_presigned_url(
    upload_url: str, file_path: str, upload_headers: Optional[Dict[str, str]] = None
) -> bool:
    if not os.path.exists(file_path):
        logger.info(f"❌ FAIL: File not found: {file_path}", "ERROR")
        return False
    with open(file_path, "rb") as f:
        file_data = f.read()
    headers = upload_headers if upload_headers else {}
    logger.info(
        f"Uploading file: {file_path} ({len(file_data)} bytes), "
        f"Upload headers: {headers}"
    )
    response = requests.put(upload_url, data=file_data, headers=headers, timeout=60)
    if response.status_code in [200, 204]:
        return True
    else:
        logger.exception(
            f"❌ FAIL: Upload failed with status {response.status_code}, Response: {response.text}"
        )
        raise Exception(
            f"❌ FAIL: Upload failed with status {response.status_code}, Response: {response.text}"
        )


async def main():
    # 检查Celery配置
    from app.core.config import app_config

    print(f"\n{'='*60}")
    print(f"🔧 Celery配置检查:")
    print(f"  消息代理类型: {app_config.MESSAGE_BROKER_TYPE}")
    print(f"  Broker URL: {app_config.get_celery_broker_url()}")
    print(f"  Result Backend: {app_config.get_celery_result_backend()}")
    print(f"{'='*60}\n")

    # orchestrator = KBOrchestrator()
    # db = get_db()
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    user_id = "fbab1e38-9b11-4cb2-89cd-bfd8d69d18e4"
    print(f"user_id:{user_id}")

    # 1. 初始化用户配置（模拟正式项目的流程）
    logger.info("正在初始化用户配置...")
    user_config_str = UserConfigService.init_user(user_id)
    user_config = (
        json.loads(user_config_str)
        if isinstance(user_config_str, str)
        else user_config_str
    )
    logger.info(f"用户配置初始化完成: {user_config.get('user')}")

    # 2. 准备文件信息
    source_file_name = "测试文档.docx"
    s3_key = f"uploads/{job_id}.docx"

    # 3. 创建解析参数（模拟 ParsingParams）
    parsing_params = {
        "model": "base",
        "ocr_enabled": False,
        "kb_dir": "默认目录",
        "doc_type": "auto",
        "smart_title_parse": True,
        "summary_image": True,
        "summary_table": False,
        "summary_txt": False,
        "add_frag_desc": "",
    }

    # 4. 创建模拟的 JobCreate 请求（用于构建 metadata）
    original_request = {
        "source_type": "file",
        "file_name": source_file_name,
        "data_id": None,
        "parsing_params": parsing_params,
        "webhook": None,
    }

    # 5. 直接创建完整的 metadata（包含 user_config，模拟 JobMetadataHelper.create_from_request）
    job_metadata = {
        "original_request": original_request,
        "parsing_params": parsing_params,
        "data_id": None,
        "webhook": None,
        "user_config": user_config,  # 关键：必须包含 user_config
        "source_type": "file",
        "source_file_name": source_file_name,
        "source_url": None,
        "file_url": None,
    }

    logger.info(
        f"Job metadata 创建完成，包含 user_config: {'user_config' in job_metadata}"
    )

    # 6. 上传文件
    upload_service = FileUploadService()
    upload_info = await upload_service.generate_upload_url(job_id, ".docx")
    print("upload_info", upload_info)
    upload_url = upload_info["upload_url"]
    upload_headers = upload_info["upload_headers"]
    upload_file_to_presigned_url(upload_url, "data/测试文档.docx", upload_headers)

    # 7. 创建 Job（使用包含 user_config 的 metadata）
    async with get_db_context() as db:
        job_repo = JobRepository()
        await job_repo.create_job(
            db=db,
            job_id=job_id,
            user_id=user_id,
            job_type="kb_management",
            source_type="file",  # 改为 file，因为是通过文件上传
            file_path=None,
            webhook_url=None,
            metadata=job_metadata,  # 使用包含 user_config 的完整 metadata
            initial_state="waiting-file",
            s3_key=s3_key,  # 预设s3_key
        )
        logger.info(f"Job 创建成功: {job_id}")

    # doc_url = "https://sj11tos.qmzhiku.com/review/咸阳市秦都区人民西路小学建设项目吊篮专项施工方案（修改）.docx"
    # await orchestrator.start_workflow(
    #     db=db,
    #     job_id=job_id,
    #     source_type='file',
    #     file_path='../data/测试文档.docx',
    #     file_url=doc_url,  # 需要从metadata获取
    #     user_id=str('aaa')
    # )
    result_aa = await _parse_and_vectorize_async(job_id, user_id)
    result_bb = await _store_to_db_async(result_aa, user_id)
    result_cc = await _send_webhook_async(result_bb, user_id)
    print(result_cc)


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
