"""
知识库管理Celery任务
"""
import asyncio
import json
import os
import uuid
from typing import Dict, Any, Optional
from celery import Task
from loguru import logger

from app.core.celery_app import get_celery_app
from app.core.state_machine.states import JobStatus  # 仅用于状态常量，不直接操作状态机
# Worker 不再直接访问数据库，从 Redis 获取信息
from app.services.redis import RedisServiceFactory, JobInfoRedisService, JobMetadataService
from app.services.storage.file_upload_service import FileUploadService
from app.core.database import get_db_context
from app.core.config import settings
from app.utils.json_utils import make_json_safe
from app.services.messaging import get_message_publisher

# 获取Celery应用
celery_app = get_celery_app()


class KBBaseTask(Task):
    """知识库基础任务类"""
    
    def on_success(self, retval, task_id, args, kwargs):
        """任务成功回调"""
        logger.info(f"知识库任务 {task_id} 执行成功")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败回调"""
        logger.error(f"知识库任务 {task_id} 执行失败: {exc}")
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """任务重试回调"""
        logger.warning(f"知识库任务 {task_id} 重试: {exc}")
        
        # 获取job_id（从args或kwargs中）
        job_id = None
        if args and len(args) > 0:
            if isinstance(args[0], dict) and 'job_id' in args[0]:
                job_id = args[0]['job_id']
            elif isinstance(args[0], str):
                job_id = args[0]
        elif 'job_id' in kwargs:
            job_id = kwargs['job_id']
        
        if job_id:
            # 发布重试消息（通过消息通知API服务处理重试状态）
            try:
                message_publisher = get_message_publisher()
                message_publisher.publish_status_update(
                    job_id=job_id,
                    status=JobStatus.RUNNING.value,  # 重试时保持running状态
                    trigger="task_retry",
                    metadata={
                        "retry_count": self.request.retries,
                        "error_message": str(exc),
                        "task_id": task_id
                    },
                    operator_type="system",
                    async_mode=False
                )
                logger.info(f"任务重试消息已发布: job_id={job_id}, retry_count={self.request.retries}")
            except Exception as e:
                logger.error(f"发布重试消息失败: {e}")


# 文件上传任务已移除 - 文件通过S3直传处理


@celery_app.task(bind=True, base=KBBaseTask, name='app.core.tasks.kb_tasks.upload_url_file_task')
def upload_url_file_task(self, job_id: str, source_url: str, user_id: str = None, job_type: str = None):
    """URL文件下载并上传到S3任务"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Event loop is closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(_upload_url_file_async(
            job_id, source_url, user_id, job_type
        ))
        return result
    except Exception as e:
        logger.error(f"URL文件上传任务失败: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)
    finally:
        if loop != asyncio.get_event_loop():
            loop.close()


async def _upload_url_file_async(job_id: str, source_url: str, user_id: str, job_type: str = None):
    """异步URL文件下载并上传到S3"""
    message_publisher = get_message_publisher()
    
    # 从Redis获取Job信息
    try:
        redis_service = RedisServiceFactory.get_service()
        job_info_service = JobInfoRedisService(redis_service)
        job_info = await job_info_service.get_job_info(job_id)
        
        if not job_info:
            # 如果Redis中没有，尝试从job_metadata中获取
            metadata_service = JobMetadataService(redis_service)
            job_metadata = await metadata_service.get_metadata(job_id)
            if job_metadata:
                # 从metadata中提取s3_key（如果存在）
                s3_key = job_metadata.get("s3_key")
                if not s3_key:
                    raise ValueError(f"Job信息不存在: job_id={job_id}")
            else:
                raise ValueError(f"Job信息不存在: job_id={job_id}")
        else:
            s3_key = job_info.get("s3_key")
            if not s3_key:
                raise ValueError(f"Job信息中缺少s3_key: job_id={job_id}")
        
        # 发布进度更新消息：验证文件类型
        message_publisher.publish_progress_update(
            job_id=job_id,
            progress=3,
            message_text="正在验证URL文件类型...",
            async_mode=False
        )
        
        # 步骤1：验证URL文件类型（在下载前，防止下载不安全的文件）
        from urllib.parse import urlparse
        import os
        parsed_url = urlparse(source_url)
        url_path = parsed_url.path
        file_extension = os.path.splitext(url_path)[1].lower()
        
        # 获取支持的文件扩展名
        from app.core.constants.system import SystemConstants
        all_supported_extensions = []
        for category in SystemConstants.SUPPORTED_EXTENSIONS.values():
            all_supported_extensions.extend(category)
        
        if not file_extension or file_extension not in all_supported_extensions:
            supported_formats = ", ".join(sorted(all_supported_extensions))
            raise ValueError(f"不支持的文件类型 {file_extension}。仅支持以下格式：{supported_formats}")
        
        logger.info(f"URL文件类型验证通过: {file_extension}")
        
        # 发布进度更新消息：开始下载
        message_publisher.publish_progress_update(
            job_id=job_id,
            progress=10,
            message_text="正在从URL下载文件...",
            async_mode=False
        )
        
        # 步骤2：下载文件到临时目录
        upload_service = FileUploadService()
        temp_file_path = await upload_service._download_file_from_url(source_url)
        
        try:
            # 发布进度更新消息：验证文件大小
            message_publisher.publish_progress_update(
                job_id=job_id,
                progress=30,
                message_text="正在验证文件大小...",
                async_mode=False
            )
            
            # 步骤3：验证文件大小（在上传S3前）
            file_size = os.path.getsize(temp_file_path)
            MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB限制
            if file_size > MAX_FILE_SIZE:
                raise ValueError(f"文件大小超过限制：{file_size / 1024 / 1024:.2f}MB > {MAX_FILE_SIZE / 1024 / 1024}MB")
            
            logger.info(f"文件大小验证通过: {file_size / 1024 / 1024:.2f}MB")
            
            # 发布进度更新消息：上传到S3
            message_publisher.publish_progress_update(
                job_id=job_id,
                progress=50,
                message_text="正在上传文件到S3...",
                async_mode=False
            )
            
            # 步骤4：上传到S3（使用job中预设的s3_key）
            await upload_service._upload_to_s3(temp_file_path, s3_key, upload_service.uploads_bucket)
            
            logger.info(f"文件上传S3成功: {s3_key}")
            
        finally:
            # 清理临时文件
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                logger.debug(f"临时文件已清理: {temp_file_path}")
        
        # 发布进度更新消息：验证上传结果
        message_publisher.publish_progress_update(
            job_id=job_id,
            progress=80,
            message_text="正在验证上传结果...",
            async_mode=False
        )
        
        # 步骤5：验证S3文件存在
        file_info = await upload_service.verify_s3_file_exists(s3_key)
        if not file_info.get("exists"):
            raise ValueError("S3文件验证失败")
        
        # 发布进度更新消息：完成
        message_publisher.publish_progress_update(
            job_id=job_id,
            progress=100,
            message_text="URL文件上传完成，等待处理...",
            async_mode=False
        )
        
        logger.info(f"URL文件上传完成，等待S3 webhook触发: {job_id} -> {s3_key}")
        
        return {
            "status": "success",
            "job_id": job_id,
            "s3_key": s3_key,
            "file_size": file_info.get("size")
        }
        
    except Exception as e:
        logger.error(f"URL文件上传失败: {e}")
        import traceback
        # 发布失败消息
        message_publisher.publish_failure(
            job_id=job_id,
            error_message=str(e),
            error_type=type(e).__name__,
            stack_trace=traceback.format_exc(),
            async_mode=False
        )
        raise


@celery_app.task(bind=True, base=KBBaseTask, name='app.core.tasks.kb_tasks.parse_and_vectorize_task')
def parse_and_vectorize_task(self, job_id: str, user_id: str = None, job_type: str = "kb_management"):
    """解析并向量化任务（文件已通过S3直传）"""
    try:
        if not job_id:
            raise ValueError("缺少job_id参数")
        
        # 使用更安全的方式处理异步操作
        try:
            # 尝试获取当前事件循环
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("Event loop is closed")
        except RuntimeError:
            # 如果没有事件循环或循环已关闭，创建新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(_parse_and_vectorize_async(
                job_id, user_id
            ))
            return result
        finally:
            # 只有在创建了新循环时才关闭
            if loop != asyncio.get_event_loop():
                loop.close()
            
    except Exception as e:
        logger.error(f"解析并向量化任务失败: {e}")
        raise self.retry(exc=e, countdown=120, max_retries=2)


async def _parse_and_vectorize_async(job_id: str, user_id: str):
    """异步解析并向量化（文件已通过S3直传）"""
    message_publisher = get_message_publisher()
    
    try:
        # 从Redis获取Job信息
        redis_service = RedisServiceFactory.get_service()
        job_info_service = JobInfoRedisService(redis_service)
        job_info = await job_info_service.get_job_info(job_id)
        
        if not job_info:
            raise ValueError(f"Job信息不存在: job_id={job_id}")
        
        s3_key = job_info.get("s3_key")
        if not s3_key:
            raise ValueError(f"Job信息中缺少s3_key: job_id={job_id}")
        
        job_user_id = job_info.get("user_id")
        if not job_user_id:
            job_user_id = user_id  # 回退到参数中的user_id
        
        # 验证S3文件存在性
        from app.services.storage.file_upload_service import FileUploadService
        upload_service = FileUploadService()
        file_info = await upload_service.verify_s3_file_exists(s3_key)
        if not file_info.get("exists"):
            raise ValueError(f"S3文件不存在: {s3_key}")
        
        logger.info(f"S3文件验证成功: {s3_key}")
        
        # 从job_metadata获取user_config（创建时已初始化）
        from app.models.schemas.job_metadata import JobMetadataHelper
        
        metadata_service = JobMetadataService(redis_service)
        job_metadata = await metadata_service.get_metadata(job_id)
        if not job_metadata:
            raise ValueError(f"Job metadata不存在: job_id={job_id}")
        
        user_config = JobMetadataHelper.get_user_config(job_metadata)
        
        if not user_config:
            raise ValueError("Job metadata中缺少用户配置")
        
        # 发布状态更新消息：开始处理
        # 注意：状态检查由API服务处理，Worker只负责发布状态更新消息
        message_publisher.publish_status_update(
            job_id=job_id,
            status=JobStatus.RUNNING.value,
            trigger="start_processing",
            previous_status=None,  # 由API服务确定之前的状态
            operator_type="system",
            async_mode=False
        )
        
        # 发布进度更新消息：开始解析
        message_publisher.publish_progress_update(
            job_id=job_id,
            progress=10,
            message_text="正在解析文档...",
            async_mode=False
        )
        
        logger.debug(f"开始下载文件: S3键={s3_key}")
        
        # 下载文件到本地临时目录
        from app.services.storage.file_upload_service import FileUploadService
        upload_service = FileUploadService()
        file_url_response = await upload_service.generate_download_url(s3_key, settings.S3_BUCKET_NAME)
        file_url = file_url_response["download_url"]  # 提取实际的URL字符串
        
        # 准备解析参数 - 从job_metadata获取
        filename = JobMetadataHelper.get_field(job_metadata, "source_file_name")
        logger.debug(f"filename: {filename}")
        
        # 调用修改后的解析逻辑（传入user_config）
        from app.services.knowledge.knowledge_base_service import checkerboard_inject_parse
        
        logger.debug(f"开始解析文件: {filename}, 类型: {JobMetadataHelper.get_parsing_param(job_metadata, 'doc_type', 'auto')}")
        
        add_dir = await checkerboard_inject_parse(
            file_full_path=file_url,
            filename=filename,
            user_config=user_config,  # 传入用户配置
            kb_dir=JobMetadataHelper.get_parsing_param(job_metadata, "kb_dir", "默认目录"),
            doc_type=JobMetadataHelper.get_parsing_param(job_metadata, "doc_type", "auto"),
            smart_title_parse=JobMetadataHelper.get_parsing_param(job_metadata, "smart_title_parse", True),
            summary_image=JobMetadataHelper.get_parsing_param(job_metadata, "summary_image", True),
            summary_table=JobMetadataHelper.get_parsing_param(job_metadata, "summary_table", True),
            summary_txt=JobMetadataHelper.get_parsing_param(job_metadata, "summary_txt", True),
            add_frag_desc=JobMetadataHelper.get_parsing_param(job_metadata, "add_frag_desc", ""),
        )
        
        if not add_dir:
            logger.error(f"文件解析失败，未返回解析目录: {filename}")
            raise ValueError("文件解析失败，未返回解析目录")
        
        logger.info(f"文件解析成功: {add_dir}")
        
        # 保存add_dir到Redis job_metadata（用于后续ZIP生成和调试）
        await metadata_service.update_metadata(job_id, {"add_dir": add_dir})
        logger.debug(f"add_dir已保存到Redis job_metadata: {add_dir}")
        
        # 发布进度更新消息：解析完成，开始向量化
        message_publisher.publish_progress_update(
            job_id=job_id,
            progress=30,
            message_text="解析完成，正在向量化...",
            async_mode=False
        )
        
        # 调用旧方案的向量化逻辑
        from app.services.knowledge.kb_encoder_service import encode_kb
        
        user_info = await encode_kb(user_config, add_dir=add_dir, mode="add")
        
        # 保存DataFrame为chunks到Redis
        from app.services.redis.chunks_redis_service import ChunksRedisService
        
        chunks_redis_service = ChunksRedisService(redis_service)
        
        # 单独处理当前文件解析的chunks
        from app.services.knowledge.kb_encoder_service import load_new_data
        add_contents_df = load_new_data(add_dir)
        if add_contents_df is not None:
            logger.debug(f"开始保存DataFrame为chunks: DataFrame长度={len(add_contents_df)}")
            success = await chunks_redis_service.save_dataframe_as_chunks(job_id, add_contents_df)
            if success:
                logger.info(f"DataFrame已保存为chunks到Redis: job_id={job_id}")
            else:
                logger.error(f"保存DataFrame为chunks失败: job_id={job_id}")
        else:
            logger.warning("add_contents_df为空，保存空chunks到Redis")
            await chunks_redis_service.save_chunks(job_id, [])
        
        # 发布进度更新消息：向量化完成，开始生成ZIP
        message_publisher.publish_progress_update(
            job_id=job_id,
            progress=70,
            message_text="向量化完成，正在生成结果包...",
            async_mode=False
        )
        
        # 从Redis获取chunks数据（用于生成ZIP包）
        chunks = await chunks_redis_service.get_chunks(job_id)
        if chunks:
            logger.info(f"从Redis获取chunks数据成功: job_id={job_id}, count={len(chunks)}")
        else:
            logger.warning(f"从Redis获取chunks数据失败: job_id={job_id}")
            chunks = []
        
        # 从全局管理器获取向量化结果（用于准备存储到knowledge_base表的数据）
        from app.services.common.global_manager_service import global_df_manager
        user_key = f"{user_config['user']}_all_contents_df"
        all_contents_df = global_df_manager.get_dataframe(user_key)
        logger.debug(f"user_key: {user_key}, all_contents_df length: {len(all_contents_df) if all_contents_df is not None else 'None'}")
        
        # 准备知识库记录数据（转换为字典格式，用于消息传递）
        kb_records = []
        if all_contents_df is not None and len(all_contents_df) > 0:
            from app.models.database.knowledge_base import KBPydantic
            
            # 转换DataFrame为字典（只处理新增的内容）
            contents_count = len(all_contents_df)
            for _, row in all_contents_df.tail(contents_count).iterrows():
                kb_record_dict = {
                    'content': row.get('content'),
                    'path': row.get('path'),
                    'type': row.get('type'),
                    'length': row.get('length'),
                    'keywords': row.get('keywords'),
                    'summary': row.get('summary'),
                    'know_id': row.get('know_id'),
                    'tokens': row.get('tokens'),
                    'embedding': None  # 向量存储在文件系统
                }
                kb_records.append(kb_record_dict)
        
        # 从job_metadata获取信息
        source_file_name = JobMetadataHelper.get_field(job_metadata, "source_file_name") or JobMetadataHelper.get_field(job_metadata, "source_url")
        if isinstance(source_file_name, str) and "/" in source_file_name:
            source_file_name = os.path.basename(source_file_name)
        
        # 获取 data_id
        data_id = JobMetadataHelper.get_field(job_metadata, "data_id")
        
        # 发布进度更新消息：生成ZIP包
        message_publisher.publish_progress_update(
            job_id=job_id,
            progress=80,
            message_text="正在生成ZIP包...",
            async_mode=False
        )
        
        # 生成 ZIP 包（业务逻辑处理）
        from app.services.storage.zip_result_service import ZipResultService
        zip_service = ZipResultService()
        zip_file_path, checksum, statistics, zip_size = zip_service.generate_zip_package(
            job_id=job_id,
            chunks=chunks,
            add_dir=add_dir,
            source_file_name=source_file_name,
            data_id=data_id,
            job_metadata=job_metadata,
        )
        
        # 发布进度更新消息：上传ZIP到S3
        message_publisher.publish_progress_update(
            job_id=job_id,
            progress=90,
            message_text="正在上传结果到S3...",
            async_mode=False
        )
        
        # 上传 ZIP 包到 S3（业务逻辑处理）
        result_s3_key = await upload_service.upload_zip_result(job_id, zip_file_path)
        
        # 安全地获取kb_records的长度
        stored_count = len(kb_records) if kb_records is not None else 0
        
        # 发布进度更新消息：任务完成
        message_publisher.publish_progress_update(
            job_id=job_id,
            progress=100,
            message_text="任务完成！",
            async_mode=False
        )
        
        # 发布结果消息（包含所有需要存储的数据）
        message_publisher.publish_result(
            job_id=job_id,
            chunks_job_id=job_id,  # chunks数据通过job_id从Redis读取
            result_s3_key=result_s3_key,
            checksum=checksum,
            zip_size=zip_size,
            stored_count=stored_count,
            kb_records=kb_records,  # 知识库记录数据
            statistics=statistics,
            delivery_mode="url",
            add_dir=add_dir,
            async_mode=False
        )
        
        logger.info(f"Worker处理完成，结果消息已发布: job_id={job_id}, stored_count={stored_count}, result_s3_key={result_s3_key}")
        
        return {
            "status": "success",
            "job_id": job_id,
            "add_dir": add_dir,
            "vectors_count": len(user_info.get("all_vec", [])),
            "contents_count": len(user_info.get("all_contents_df", [])),
            "stored_count": stored_count,
            "delivery_mode": "url",
            "result_s3_key": result_s3_key
        }
            
    except Exception as e:
        logger.error(f"解析并向量化失败: {e}")
        import traceback
        # 发布失败消息
        message_publisher = get_message_publisher()
        message_publisher.publish_failure(
            job_id=job_id,
            error_message=str(e),
            error_type=type(e).__name__,
            stack_trace=traceback.format_exc(),
            async_mode=False
        )
        raise


# store_to_db_task 已移除，逻辑已合并到 parse_and_vectorize_task 中




# Webhook和邮件发送已迁移到API服务处理
# Worker只负责业务逻辑处理，完成后通过消息通知API服务
# API服务根据数据库查询信息处理Webhook和邮件发送
