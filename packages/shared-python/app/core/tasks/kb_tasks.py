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
from app.core.state_machine import JobStatus  # 仅用于状态常量，不直接操作状态机
from app.repositories.job_repository import JobRepository  # 仅用于只读操作
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
    job_repo = JobRepository()
    message_publisher = get_message_publisher()
    
    # 初始化Redis服务（用于进度更新，但改为消息发布）
    try:
        # 第一次数据库连接：获取Job信息
        async with get_db_context() as db:
            job = await job_repo.get_job_by_id(db, job_id)
            if not job:
                raise ValueError("Job不存在")
            s3_key = job.s3_key  # 提前获取s3_key，避免后续数据库连接问题
        
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
    job_repo = JobRepository()
    message_publisher = get_message_publisher()
    
    try:
        async with get_db_context() as db:
            # 获取Job
            job = await job_repo.get_job_by_id(db, job_id)
            if not job:
                raise ValueError("Job不存在")
            
            # 验证S3文件存在性
            if not job.s3_key:
                raise ValueError("Job缺少S3键信息")
            
            from app.services.storage.file_upload_service import FileUploadService
            upload_service = FileUploadService()
            file_info = await upload_service.verify_s3_file_exists(job.s3_key)
            if not file_info.get("exists"):
                raise ValueError(f"S3文件不存在: {job.s3_key}")
            
            logger.info(f"S3文件验证成功: {job.s3_key}")
            
            # 动态获取用户配置
            from app.services.redis.user_redis_service import UserRedisService
            from app.services.user.user_config_service import UserConfigService
            from app.services.redis import RedisServiceFactory
            import json
            
            redis_service = RedisServiceFactory.get_service()
            user_redis_service = UserRedisService(redis_service)
            
            # 尝试从Redis获取用户配置
            user_id_str = str(job.user_id)  # 确保user_id是字符串
            user_config = await user_redis_service.get_user_config(user_id_str)
            
            if not user_config:
                # 如果Redis中没有，则初始化用户配置
                logger.info(f"Redis中未找到用户 {user_id_str} 配置，正在初始化...")
                user_config_str = UserConfigService.init_user(user_id_str)
                user_config = json.loads(user_config_str) if isinstance(user_config_str, str) else user_config_str
                
                # 保存到Redis
                await user_redis_service.save_user_config(user_id_str, user_config)
                logger.info(f"用户 {user_id_str} 配置初始化并保存到Redis")
            
            if not user_config:
                raise ValueError("用户配置为空")
            
            # 从job_metadata直接获取user_config（创建时已初始化）
            from app.services.redis import RedisServiceFactory
            from app.models.schemas.job_metadata import JobMetadataHelper
            
            redis_service = RedisServiceFactory.get_service()
            job_metadata = await job_repo.get_job_metadata(db, job_id, redis_service)
            user_config = JobMetadataHelper.get_user_config(job_metadata)
            
            if not user_config:
                raise ValueError("Job metadata中缺少用户配置")
            
            # 检查当前状态，如果是failed，先发布状态更新消息转换到pending
            if job.status == JobStatus.FAILED.value:
                message_publisher.publish_status_update(
                    job_id=job_id,
                    status=JobStatus.PENDING.value,
                    trigger="retry_from_failed",
                    previous_status=job.status,
                    operator_type="system",
                    async_mode=False
                )
            
            # 发布状态更新消息：开始处理
            message_publisher.publish_status_update(
                job_id=job_id,
                status=JobStatus.RUNNING.value,
                trigger="start_processing",
                previous_status=job.status if job.status != JobStatus.FAILED.value else JobStatus.PENDING.value,
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
            
            # 获取S3键和文件信息
            s3_key = job.s3_key
            
            # 验证必要参数
            if not s3_key:
                logger.error(f"Job {job_id} 缺少S3键信息")
                raise ValueError("Job缺少S3键信息")
            
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
            from app.services.redis import RedisServiceFactory
            
            redis_service = RedisServiceFactory.get_service()
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
            
            # 发布进度更新消息：向量化完成
            message_publisher.publish_progress_update(
                job_id=job_id,
                progress=70,
                message_text="向量化完成，正在存储到数据库...",
                async_mode=False
            )
            
            return {
                "status": "success",
                "job_id": job_id,
                "add_dir": add_dir,
                "vectors_count": len(user_info.get("all_vec", [])),
                "contents_count": len(user_info.get("all_contents_df", []))
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


@celery_app.task(bind=True, base=KBBaseTask, name='app.core.tasks.kb_tasks.store_to_db_task')
def store_to_db_task(self, prev_result: dict, user_id: str = None, job_type: str = "kb_management"):
    """存储到数据库任务"""
    try:
        # 从上一个任务的结果中获取job_id
        job_id = prev_result.get("job_id")
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
            result = loop.run_until_complete(_store_to_db_async(
                prev_result, user_id
            ))
            return result
        finally:
            # 只有在创建了新循环时才关闭
            if loop != asyncio.get_event_loop():
                loop.close()
            
    except Exception as e:
        logger.error(f"存储数据库任务失败: {e}")
        raise self.retry(exc=e, countdown=120, max_retries=2)


async def _store_to_db_async(prev_result: dict, user_id: str):
    """异步存储到数据库（Worker处理业务逻辑，通过消息通知API服务存储）"""
    job_repo = JobRepository()
    message_publisher = get_message_publisher()
    
    try:
        # 从上一个任务的结果中获取job_id
        job_id = prev_result.get("job_id")
        if not job_id:
            raise ValueError("缺少job_id参数")
            
        async with get_db_context() as db:
            # 获取Job（只读，用于获取必要信息）
            job = await job_repo.get_job_by_id(db, job_id)
            if not job:
                raise ValueError("Job不存在")
            
            # 从job_metadata获取用户配置（创建时已初始化）
            from app.services.redis import RedisServiceFactory
            from app.models.schemas.job_metadata import JobMetadataHelper
            
            redis_service = RedisServiceFactory.get_service()
            job_metadata = await job_repo.get_job_metadata(db, job_id, redis_service)
            user_config = JobMetadataHelper.get_user_config(job_metadata)
            
            if not user_config:
                raise ValueError("Job metadata中缺少用户配置")
            
            # 发布进度更新消息：开始存储数据库
            message_publisher.publish_progress_update(
                job_id=job_id,
                progress=80,
                message_text="正在存储到数据库...",
                async_mode=False
            )
            
            # 从Redis获取chunks数据（用于生成ZIP包）
            from app.services.redis.chunks_redis_service import ChunksRedisService
            
            chunks_redis_service = ChunksRedisService(redis_service)
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
            source_file_name = JobMetadataHelper.get_field(job_metadata, "source_file_name") or job.file_path or JobMetadataHelper.get_field(job_metadata, "source_url")
            if isinstance(source_file_name, str) and "/" in source_file_name:
                source_file_name = os.path.basename(source_file_name)

            # 从 prev_result 获取 add_dir
            add_dir = prev_result.get("add_dir")
            if not add_dir:
                raise ValueError("缺少 add_dir 参数，无法生成 ZIP 包")

            # 获取 data_id
            data_id = JobMetadataHelper.get_field(job_metadata, "data_id")

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

            # 上传 ZIP 包到 S3（业务逻辑处理）
            upload_service = FileUploadService()
            result_s3_key = await upload_service.upload_zip_result(job_id, zip_file_path)

            # 发布进度更新消息：数据库存储完成
            message_publisher.publish_progress_update(
                job_id=job_id,
                progress=95,
                message_text="数据库存储完成，正在生成结果...",
                async_mode=False
            )
            
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

            logger.info(f"Worker处理完成，结果消息已发布: job_id={job_id}, stored_count={stored_count}")

            return {
                "status": "success",
                "job_id": job_id,
                "stored_count": stored_count,
                "delivery_mode": "url",
                "result_s3_key": result_s3_key
            }
            
    except Exception as e:
        logger.error(f"存储数据库失败: {e}")
        import traceback
        # 发布失败消息
        message_publisher.publish_failure(
            job_id=job_id if 'job_id' in locals() else "unknown",
            error_message=str(e),
            error_type=type(e).__name__,
            stack_trace=traceback.format_exc(),
            async_mode=False
        )
        raise




@celery_app.task(bind=True, base=KBBaseTask, name='app.core.tasks.kb_tasks.send_webhook_task')
def send_webhook_task(self, prev_result: dict, user_id: str = None, job_type: str = "kb_management"):
    """发送Webhook任务（独立步骤，失败不影响主任务）"""
    try:
        # 从上一个任务的结果中获取job_id
        job_id = prev_result.get("job_id")
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
            result = loop.run_until_complete(_send_webhook_async(prev_result, user_id))
            return result
        finally:
            # 只有在创建了新循环时才关闭
            if loop != asyncio.get_event_loop():
                loop.close()
            
    except Exception as e:
        logger.error(f"发送Webhook任务失败（第{self.request.retries + 1}次）: {e}")
        # 独立重试机制：最多5次，间隔递增（60s, 120s, 240s, 480s, 960s）
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries), max_retries=5)


async def _send_webhook_async(prev_result: dict, user_id: str):
    """异步发送Webhook"""
    job_repo = JobRepository()
    
    try:
        # 从上一个任务的结果中获取job_id
        job_id = prev_result.get("job_id")
        if not job_id:
            raise ValueError("缺少job_id参数")
            
        async with get_db_context() as db:
            # 获取Job信息
            job = await job_repo.get_job_by_id(db, job_id)
            if not job:
                logger.warning(f"Job {job_id} 不存在，跳过Webhook")
                return {"status": "skipped", "webhook_sent": False}
            
            # 从job_metadata获取webhook配置
            from app.services.redis import RedisServiceFactory
            from app.models.schemas.job_metadata import JobMetadataHelper
            
            redis_service = RedisServiceFactory.get_service()
            job_metadata = await job_repo.get_job_metadata(db, job_id, redis_service)
            webhook_config = JobMetadataHelper.get_webhook(job_metadata)
            
            # 检查是否需要发送Webhook
            if not job.webhook_enabled or not webhook_config or not webhook_config.get("url"):
                logger.info(f"Job {job_id} Webhook未启用，跳过")
                return {"status": "skipped", "webhook_sent": False}
            
            # 获取结果数据
            from app.repositories.job_result_repository import JobResultRepository
            job_result_repo = JobResultRepository()
            job_result = await job_result_repo.get_by_job_id(db, job_id)
            if not job_result:
                logger.warning(f"Job {job_id} 尚未生成结果，跳过Webhook")
                return {"status": "skipped", "webhook_sent": False}

            upload_service = FileUploadService()

            # 调用Webhook服务
            from app.services.webhook.webhook_service import WebhookService
            from datetime import datetime
            webhook_service = WebhookService()

            webhook_payload: Dict[str, Any] = {
                "job_id": job_id,
                "status": "completed",
                "delivery_mode": "url",  # 固定为 url 模式
                "completed_at": datetime.utcnow().isoformat()
            }

            # 添加 result_url（ZIP 包下载链接）
            if job_result.result_s3_key:
                result_url_info = await upload_service.generate_download_url(job_result.result_s3_key)
                webhook_payload["result_url"] = result_url_info["download_url"]
            
            # 添加 result（包含 checksum 和 statistics）
            if job_result.inline_payload:
                webhook_payload["result"] = job_result.inline_payload

            webhook_result = await webhook_service.send_webhook(
                job_id=job_id,
                webhook_url=webhook_config["url"],
                payload=webhook_payload
            )
            
            logger.info(f"Webhook发送完成: job_id={job_id}, result={webhook_result}")
            
            return {
                "status": "success",
                "job_id": job_id,
                "webhook_result": webhook_result
            }
            
    except Exception as e:
        logger.error(f"发送Webhook失败: {e}")
        # Webhook失败不标记Job为失败，仅抛出异常触发重试
        raise


async def _send_job_completion_email(db, job_id: str, job_type: str, result_s3_key: str = None):
    """发送任务完成邮件"""
    try:
        from app.services.email import EmailService
        from app.repositories.job_repository import JobRepository
        from app.services.storage.file_upload_service import FileUploadService
        job_result_repo = JobResultRepository()
        
        # 获取Job信息
        job_repo = JobRepository()
        job = await job_repo.get_job_by_id(db, job_id)
        
        if job and job.webhook_enabled:
            # 生成下载链接（如果有结果文件）
            download_url = None
            if not result_s3_key:
                job_result = await job_result_repo.get_by_job_id(db, job_id)
                if job_result and job_result.result_s3_key:
                    result_s3_key = job_result.result_s3_key
            if result_s3_key:
                upload_service = FileUploadService()
                download_url = await upload_service.generate_download_url(result_s3_key)
            
            # 获取用户信息
            from sqlalchemy import select
            from app.models.database.user import User
            result = await db.execute(select(User).where(User.id == job.user_id))
            user = result.scalar_one_or_none()
            
            if user:
                email_service = EmailService()
                await email_service.send_job_completion_email(
                    user_email=user.email,
                    job_type=job_type,
                    job_id=job_id,
                    download_url=download_url,
                    user_name=getattr(user, 'full_name', None) or user.email
                )
                
                logger.info(f"任务完成邮件已发送给用户 {user.email}")
                
    except Exception as e:
        logger.error(f"发送任务完成邮件失败: {e}")
        # 不抛出异常，避免影响任务完成
