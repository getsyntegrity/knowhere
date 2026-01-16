"""
知识库管理Celery任务
"""
import asyncio
import os
from typing import Dict, Any, Optional
from celery import Task
from loguru import logger

from shared.core.celery_app import get_celery_app
from shared.core.state_machine.states import JobStatus
from shared.services.redis import RedisServiceFactory, JobInfoRedisService, JobMetadataService                                                                     
from shared.services.storage.file_upload_service import FileUploadService
from shared.core.config import settings
from shared.services.messaging import get_message_publisher
from shared.services.messaging.message_publisher import run_async_publish

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
                run_async_publish(
                    message_publisher.publish_status_update(
                        job_id=job_id,
                        status=JobStatus.RUNNING.value,  # 重试时保持running状态
                        trigger="task_retry",
                        metadata={
                            "retry_count": self.request.retries,
                            "error_message": str(exc),
                            "task_id": task_id
                        },
                        operator_type="system"
                    )
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
        await message_publisher.publish_progress_update(
            job_id=job_id,
            progress=3,
            message_text="正在验证URL文件类型..."
        )
        
        # 步骤1：验证URL文件类型（在下载前，防止下载不安全的文件）
        from urllib.parse import urlparse
        import os
        parsed_url = urlparse(source_url)
        url_path = parsed_url.path
        file_extension = os.path.splitext(url_path)[1].lower()
        
        # 获取支持的文件扩展名
        from shared.core.constants.system import SystemConstants
        all_supported_extensions = []
        for category in SystemConstants.SUPPORTED_EXTENSIONS.values():
            all_supported_extensions.extend(category)
        
        if not file_extension or file_extension not in all_supported_extensions:
            supported_formats = ", ".join(sorted(all_supported_extensions))
            raise ValueError(f"不支持的文件类型 {file_extension}。仅支持以下格式：{supported_formats}")                                                         
        
        logger.info(f"URL文件类型验证通过: {file_extension}")
        
        # 发布进度更新消息：开始下载
        await message_publisher.publish_progress_update(
            job_id=job_id,
            progress=10,
            message_text="正在从URL下载文件...",
        )
        
        # 步骤2：下载文件到临时目录
        upload_service = FileUploadService()
        temp_file_path = await upload_service._download_file_from_url(source_url)                                                                               
        
        try:
            # 发布进度更新消息：验证文件大小
            await message_publisher.publish_progress_update(
                job_id=job_id,
                progress=30,
                message_text="正在验证文件大小..."
            )
            
            # 步骤3：验证文件大小（在上传S3前）
            file_size = os.path.getsize(temp_file_path)
            MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB限制
            if file_size > MAX_FILE_SIZE:
                raise ValueError(f"文件大小超过限制：{file_size / 1024 / 1024:.2f}MB > {MAX_FILE_SIZE / 1024 / 1024}MB")                                        
            
            logger.info(f"文件大小验证通过: {file_size / 1024 / 1024:.2f}MB")
            
            # 发布进度更新消息：上传到S3
            await message_publisher.publish_progress_update(
                job_id=job_id,
                progress=50,
                message_text="正在上传文件到S3..."
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
        await message_publisher.publish_progress_update(
            job_id=job_id,
            progress=80,
            message_text="正在验证上传结果...",
        )
        
        # 步骤5：验证S3文件存在
        file_info = await upload_service.verify_s3_file_exists(s3_key)
        if not file_info.get("exists"):
            raise ValueError("S3文件验证失败")
        
        # 发布进度更新消息：完成
        await message_publisher.publish_progress_update(
            job_id=job_id,
            progress=100,
            message_text="URL文件上传完成，等待处理...",
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
        await message_publisher.publish_failure(
            job_id=job_id,
            error_message=str(e),
            error_type=type(e).__name__,
            stack_trace=traceback.format_exc(),
        )
        raise


@celery_app.task(bind=True, base=KBBaseTask, name='app.core.tasks.kb_tasks.parse_and_vectorize_task')                                                           
def parse_and_vectorize_task(self, job_id: str, user_id: str = None, job_type: str = "kb_management"):                                                          
    """解析任务（文件已通过S3直传） """
    logger.info(f"任务开始执行: task_id={self.request.id}, job_id={job_id}, user_id={user_id}, job_type={job_type}")
    try:
        if not job_id:
            logger.error(f"缺少job_id参数: task_id={self.request.id}")
            raise ValueError("缺少job_id参数")
        
        # 使用更安全的方式处理异步操作
        logger.info(f"开始处理事件循环: task_id={self.request.id}, job_id={job_id}")
        try:
            # 尝试获取当前事件循环
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                logger.warning(f"事件循环已关闭，将创建新循环: task_id={self.request.id}, job_id={job_id}")
                raise RuntimeError("Event loop is closed")
            logger.info(f"获取到现有事件循环: task_id={self.request.id}, job_id={job_id}")
        except RuntimeError:
            # 如果没有事件循环或循环已关闭，创建新的
            logger.info(f"创建新事件循环: task_id={self.request.id}, job_id={job_id}")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            logger.info(f"开始执行异步函数: task_id={self.request.id}, job_id={job_id}")
            
            # 计算是否为最后一次重试
            max_retries = settings.KB_TASK_MAX_RETRIES
            is_final_attempt = self.request.retries >= max_retries
            logger.info(f"Retry status: current={self.request.retries}, max={max_retries}, is_final={is_final_attempt}")
            
            result = loop.run_until_complete(_parse_and_vectorize_async(
                job_id, user_id, is_final_attempt=is_final_attempt
            ))
            logger.info(f"异步函数执行完成: task_id={self.request.id}, job_id={job_id}, result keys={list(result.keys()) if isinstance(result, dict) else None}")
            return result
        finally:
            # 只有在创建了新循环时才关闭
            if loop != asyncio.get_event_loop():
                logger.info(f"关闭事件循环: task_id={self.request.id}, job_id={job_id}")
                loop.close()
            
    except Exception as e:
        logger.error(f"解析并向量化任务失败: task_id={self.request.id}, job_id={job_id}, error={e}", exc_info=True)
        raise self.retry(exc=e, countdown=settings.KB_TASK_RETRY_COUNTDOWN, max_retries=settings.KB_TASK_MAX_RETRIES)


async def _parse_and_vectorize_async(job_id: str, user_id: str, is_final_attempt: bool = False):
    """异步解析并向量化（文件已通过S3直传）"""
    logger.info(f"异步函数开始执行: job_id={job_id}, user_id={user_id}, is_final_attempt={is_final_attempt}")
    message_publisher = get_message_publisher()
    logger.info(f"消息发布器获取成功: job_id={job_id}")
    
    try:
        # 从Redis获取Job信息
        logger.info(f"开始获取Redis服务: job_id={job_id}")
        redis_service = RedisServiceFactory.get_service()
        logger.info(f"Redis服务获取成功: job_id={job_id}")
        job_info_service = JobInfoRedisService(redis_service)
        logger.info(f"JobInfoRedisService创建成功，开始获取job_info: job_id={job_id}")
        job_info = await job_info_service.get_job_info(job_id)
        logger.info(f"job_info获取完成: job_id={job_id}, job_info存在={job_info is not None}")
        
        if not job_info:
            logger.error(f"Job信息不存在: job_id={job_id}")
            raise ValueError(f"Job信息不存在: job_id={job_id}")
        
        s3_key = job_info.get("s3_key")
        logger.info(f"s3_key提取完成: job_id={job_id}, s3_key={s3_key}")
        if not s3_key:
            logger.error(f"Job信息中缺少s3_key: job_id={job_id}, job_info keys={list(job_info.keys()) if job_info else None}")
            raise ValueError(f"Job信息中缺少s3_key: job_id={job_id}")
        
        job_user_id = job_info.get("user_id")
        if not job_user_id:
            job_user_id = user_id  # 回退到参数中的user_id
        logger.info(f"user_id确定: job_id={job_id}, job_user_id={job_user_id}")
        
        # 验证S3文件存在性
        logger.info(f"开始验证S3文件存在性: job_id={job_id}, s3_key={s3_key}")
        from shared.services.storage.file_upload_service import FileUploadService
        upload_service = FileUploadService()
        logger.info(f"FileUploadService创建成功，开始验证文件: job_id={job_id}")
        file_info = await upload_service.verify_s3_file_exists(s3_key)
        logger.info(f"S3文件验证完成: job_id={job_id}, exists={file_info.get('exists')}")
        if not file_info.get("exists"):
            logger.error(f"S3文件不存在: job_id={job_id}, s3_key={s3_key}")
            raise ValueError(f"S3文件不存在: {s3_key}")
        
        logger.info(f"S3文件验证成功: {s3_key}")
        
        # 从job_metadata获取user_config（创建时已初始化）
        logger.info(f"开始获取job_metadata: job_id={job_id}")
        from shared.models.schemas.job_metadata import JobMetadataHelper
        
        metadata_service = JobMetadataService(redis_service)
        logger.info(f"metadata_service创建成功，开始获取metadata: job_id={job_id}")
        job_metadata = await metadata_service.get_metadata(job_id)
        logger.info(f"job_metadata获取完成: job_id={job_id}, metadata存在={job_metadata is not None}")
        if not job_metadata:
            logger.error(f"Job metadata不存在: job_id={job_id}")
            raise ValueError(f"Job metadata不存在: job_id={job_id}")
        
        logger.info(f"开始从job_metadata提取user_config: job_id={job_id}")
        user_config = JobMetadataHelper.get_user_config(job_metadata)
        logger.info(f"user_config提取完成: job_id={job_id}, user_config存在={user_config is not None}")
        
        if not user_config:
            logger.error(f"Job metadata中缺少用户配置: job_id={job_id}")
            raise ValueError("Job metadata中缺少用户配置")
        
        # 强制使用配置的绝对路径
        parent_path = settings.USERS_DATA_PATH
        if not parent_path:
            raise ValueError("USERS_DATA_PATH 未配置，必须设置用户数据目录的绝对路径")
        
        if not os.path.isabs(parent_path):
            raise ValueError(f"USERS_DATA_PATH 必须是绝对路径，当前值: {parent_path}")
        
        # 验证路径是否存在或可创建
        try:
            os.makedirs(parent_path, exist_ok=True)
        except (OSError, PermissionError) as e:
            raise ValueError(f"USERS_DATA_PATH 目录无法创建或访问: {parent_path}, 错误: {e}")
        
        # 更新 user_config 中的 parent 路径
        if 'parent' in user_config:
            old_parent = user_config.get('parent', '')
            user_config['parent'] = parent_path
            if old_parent != parent_path:
                logger.info(f"路径修复: job_id={job_id}, 旧路径={old_parent}, 新路径={parent_path}")
        
        # 重新计算 KB_PATH 和 KB_VECS_PATH
        if 'KB' in user_config:
            user_config['KB_PATH'] = os.path.join(parent_path, user_config['KB'])
        if 'kb_vec_term' in user_config and 'user' in user_config:
            user_config['KB_VECS_PATH'] = os.path.join(
                parent_path,
                f"{user_config['kb_vec_term']}_{user_config['user']}"
            )
        
        # 确保用户目录结构存在（Worker服务按需创建）
        if 'KB_PATH' in user_config and 'KB_VECS_PATH' in user_config:
            from app.services.user.user_directory_service import UserDirectoryService
            try:
                UserDirectoryService.ensure_user_directories(
                    user_config['KB_PATH'],
                    user_config['KB_VECS_PATH']
                )
                logger.info(f"用户目录结构已确保存在: KB_PATH={user_config['KB_PATH']}, KB_VECS_PATH={user_config['KB_VECS_PATH']}")
            except Exception as e:
                logger.error(f"创建用户目录结构失败: {e}")
                raise ValueError(f"无法创建用户目录结构: {e}")
        
        
        # 发布状态更新消息：开始处理
        logger.info(f"开始发布状态更新消息: job_id={job_id}, status={JobStatus.RUNNING.value}")
        # 注意：状态检查由API服务处理，Worker只负责发布状态更新消息
        await message_publisher.publish_status_update(
            job_id=job_id,
            status=JobStatus.RUNNING.value,
            trigger="start_processing",
            previous_status=None,  # 由API服务确定之前的状态
            operator_type="system",
        )
        logger.info(f"状态更新消息发布成功: job_id={job_id}")
        
        # 发布进度更新消息：开始解析
        logger.info(f"开始发布进度更新消息: job_id={job_id}, progress=10")
        await message_publisher.publish_progress_update(
            job_id=job_id,
            progress=10,
            message_text="正在解析文档...",
        )
        logger.info(f"进度更新消息发布成功: job_id={job_id}")
        
        logger.info(f"开始下载文件: S3键={s3_key}, bucket={settings.S3_BUCKET_NAME}")
        
        # 下载文件到本地临时目录
        from shared.services.storage.file_upload_service import FileUploadService
        upload_service = FileUploadService()
        logger.info(f"FileUploadService创建成功，开始生成下载URL: s3_key={s3_key}")
        file_url_response = await upload_service.generate_download_url(s3_key, settings.S3_BUCKET_NAME)                                                         
        logger.info(f"下载URL生成成功: job_id={job_id}")
        file_url = file_url_response["download_url"]  # 提取实际的URL字符串
        logger.info(f"提取下载URL完成: job_id={job_id}, url长度={len(file_url) if file_url else 0}")
        
        # 准备解析参数 - 从job_metadata获取
        logger.info(f"开始准备解析参数: job_id={job_id}")
        filename = JobMetadataHelper.get_field(job_metadata, "source_file_name")
        logger.info(f"filename提取完成: job_id={job_id}, filename={filename}")
        
        # 调用修改后的解析逻辑（传入user_config）
        logger.info(f"开始导入解析服务: job_id={job_id}")
        from app.services.document_parser.parse_service import checkerboard_inject_parse                                                                     
        logger.info(f"解析服务导入成功: job_id={job_id}")
        
        doc_type = JobMetadataHelper.get_parsing_param(job_metadata, 'doc_type', 'auto')
        logger.info(f"开始解析文件: job_id={job_id}, filename={filename}, 类型={doc_type}, file_url={file_url[:100] if file_url else None}...")
        
        add_dir, add_contents_df = await checkerboard_inject_parse(
            file_full_path=file_url,
            filename=filename,
            output_dir=user_config['KB_PATH'],  # 直接传入输出目录
            kb_dir=JobMetadataHelper.get_parsing_param(job_metadata, "kb_dir", "默认目录"),                                                                     
            doc_type=JobMetadataHelper.get_parsing_param(job_metadata, "doc_type", "auto"),                                                                     
            smart_title_parse=JobMetadataHelper.get_parsing_param(job_metadata, "smart_title_parse", True),                                                     
            summary_image=JobMetadataHelper.get_parsing_param(job_metadata, "summary_image", True),                                                             
            summary_table=JobMetadataHelper.get_parsing_param(job_metadata, "summary_table", True),                                                             
            summary_txt=JobMetadataHelper.get_parsing_param(job_metadata, "summary_txt", False),                                                                 
            add_frag_desc=JobMetadataHelper.get_parsing_param(job_metadata, "add_frag_desc", ""),                                                               
        )
        logger.info(f"File parsing completed: job_id={job_id}, add_dir={add_dir}, add_contents_df length={len(add_contents_df) if add_contents_df is not None else 0}")
        
        if add_contents_df is None:
            logger.error(f"File parsing failed, no content returned: job_id={job_id}, filename={filename}")
            raise ValueError("File parsing failed, no content returned")
        
        if add_contents_df.empty:
            logger.warning(f"no content returned from file parsing: job_id={job_id}, filename={filename}")
        
        logger.info(f"文件解析成功: job_id={job_id}, add_dir={add_dir}")
        
        # 保存add_dir到Redis job_metadata（用于后续ZIP生成和调试）
        logger.info(f"开始保存add_dir到Redis: job_id={job_id}, add_dir={add_dir}")
        await metadata_service.update_metadata(job_id, {"add_dir": add_dir})
        logger.info(f"add_dir已保存到Redis job_metadata: job_id={job_id}, add_dir={add_dir}")
        
        
        # 发布进度更新消息：解析完成，准备保存chunks
        logger.info(f"开始发布进度更新消息（保存chunks）: job_id={job_id}, progress=50")
        await message_publisher.publish_progress_update(
            job_id=job_id,
            progress=50,
            message_text="解析完成，正在保存数据块...",
        )
        logger.info(f"进度更新消息发布成功（保存chunks）: job_id={job_id}")
        
        
        # 保存DataFrame为chunks到Redis
        from shared.services.redis.chunks_redis_service import ChunksRedisService
        
        chunks_redis_service = ChunksRedisService(redis_service)
        
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
        
        # 发布进度更新消息：chunks已保存，开始生成ZIP
        await message_publisher.publish_progress_update(
            job_id=job_id,
            progress=70,
            message_text="数据块已保存，正在生成结果包...",
        )
        
        # 从Redis获取chunks数据（用于生成ZIP包）
        chunks = await chunks_redis_service.get_chunks(job_id)
        if chunks:
            logger.info(f"从Redis获取chunks数据成功: job_id={job_id}, count={len(chunks)}")                                                                     
        else:
            logger.warning(f"从Redis获取chunks数据失败: job_id={job_id}")
            chunks = []
        
        # 从job_metadata获取信息
        source_file_name = JobMetadataHelper.get_field(job_metadata, "source_file_name") or JobMetadataHelper.get_field(job_metadata, "source_url")             
        if isinstance(source_file_name, str) and "/" in source_file_name:
            source_file_name = os.path.basename(source_file_name)
        
        # 获取 data_id
        data_id = JobMetadataHelper.get_field(job_metadata, "data_id")
        
        # 发布进度更新消息：生成ZIP包
        await message_publisher.publish_progress_update(
            job_id=job_id,
            progress=80,
            message_text="正在生成ZIP包...",
        )
        
        # 生成 ZIP 包（业务逻辑处理）
        from shared.services.storage.zip_result_service import ZipResultService
        zip_service = ZipResultService()
        zip_file_path, checksum, statistics, zip_size = zip_service.generate_zip_package(                                                                       
            job_id=job_id,
            chunks=chunks,
            add_dir=add_dir,
            source_file_name=source_file_name,
            data_id=data_id,
            job_metadata=job_metadata,
        )
        
        # 提取 checksum 的字符串值（ZipResultService 返回的是字典格式）
        checksum_value = checksum.get("value") if isinstance(checksum, dict) else checksum
        
        # 发布进度更新消息：上传ZIP到S3
        await message_publisher.publish_progress_update(
            job_id=job_id,
            progress=90,
            message_text="正在上传结果到S3...",
        )
        
        # 上传 ZIP 包到 S3（业务逻辑处理）
        result_s3_key = await upload_service.upload_zip_result(job_id, zip_file_path)                                                                           
        
        # 向量化已移除，stored_count 设为 0
        stored_count = 0
        kb_records = []
        
        # 发布进度更新消息：任务完成
        await message_publisher.publish_progress_update(
            job_id=job_id,
            progress=100,
            message_text="任务完成！",
        )
        
        # 发布结果消息（包含所有需要存储的数据）
        await message_publisher.publish_result(
            job_id=job_id,
            chunks_job_id=job_id,  # chunks数据通过job_id从Redis读取
            result_s3_key=result_s3_key,
            checksum=checksum_value,  # 使用提取的字符串值
            zip_size=zip_size,
            stored_count=stored_count,
            kb_records=kb_records,  # 知识库记录数据
            statistics=statistics,
            delivery_mode="url",
            add_dir=add_dir,
        )
        
        logger.info(f"Worker处理完成，结果消息已发布: job_id={job_id}, stored_count={stored_count}, result_s3_key={result_s3_key}")                             
        
        return {
            "status": "success",
            "job_id": job_id,
            "add_dir": add_dir,
            "vectors_count": 0,
            "contents_count": len(add_contents_df) if add_contents_df is not None else 0,
            "stored_count": stored_count,
            "delivery_mode": "url",
            "result_s3_key": result_s3_key
        }
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"解析并向量化失败: job_id={job_id}, error={e}, error_type={type(e).__name__}")
        logger.error(f"异常堆栈跟踪: job_id={job_id}\n{error_trace}")
        # 发布失败消息
        logger.info(f"开始发布失败消息: job_id={job_id}, refund_credits={is_final_attempt}")
        message_publisher = get_message_publisher()
        await message_publisher.publish_failure(
            job_id=job_id,
            error_message=str(e),
            error_type=type(e).__name__,
            stack_trace=error_trace,
            metadata={
                "refund_credits": is_final_attempt
            }
        )
        logger.info(f"失败消息发布完成: job_id={job_id}")
        raise


# store_to_db_task 已移除，逻辑已合并到 parse_and_vectorize_task 中

# Webhook和邮件发送已迁移到API服务处理
# Worker只负责业务逻辑处理，完成后通过消息通知API服务
# API服务根据数据库查询信息处理Webhook和邮件发送

