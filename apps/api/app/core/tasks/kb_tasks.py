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
from app.core.state_machine import JobStateMachine, KBManagementState
from app.repositories.job_repository import JobRepository
from app.repositories.job_result_repository import JobResultRepository
from app.services.storage.file_upload_service import FileUploadService
from app.core.database import get_db_context
from app.core.config import settings
from app.utils.json_utils import make_json_safe

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
        
        # 处理重试时的状态机逻辑
        try:
            import asyncio
            from app.core.state_machine import JobStateMachine
            from app.core.database import get_db_context
            
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
                # 异步处理重试状态
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
                    async def handle_retry_async():
                        state_machine = JobStateMachine()
                        async with get_db_context() as db:
                            await state_machine.handle_retry(db, job_id, {
                                "retry_count": self.request.retries,
                                "error_message": str(exc)
                            })
                    
                    loop.run_until_complete(handle_retry_async())
                finally:
                    # 只有在创建了新循环时才关闭
                    if loop != asyncio.get_event_loop():
                        loop.close()
        except Exception as e:
            logger.error(f"处理重试状态时出错: {e}")


# 文件上传任务已移除 - 文件通过S3直传处理


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
    state_machine = JobStateMachine()
    job_repo = JobRepository()
    
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
            user_config = await user_redis_service.get_user_config(job.user_id)
            
            if not user_config:
                # 如果Redis中没有，则初始化用户配置
                logger.info(f"Redis中未找到用户 {job.user_id} 配置，正在初始化...")
                user_config_str = UserConfigService.init_user(str(job.user_id))
                user_config = json.loads(user_config_str) if isinstance(user_config_str, str) else user_config_str
                
                # 保存到Redis
                await user_redis_service.save_user_config(job.user_id, user_config)
                logger.info(f"用户 {job.user_id} 配置初始化并保存到Redis")
            
            if not user_config:
                raise ValueError("用户配置为空")
            
            # 将用户配置保存到job的metadata中，供后续任务使用
            job_metadata = job.job_metadata or {}
            job_metadata["user_config"] = make_json_safe(user_config)
            job.job_metadata = job_metadata
            await db.commit()
            logger.info(f"用户配置已保存到job metadata: {job_id}")
            
            # 检查当前状态，如果是failed，先转换到pending
            if job.current_state == KBManagementState.FAILED.value:
                await state_machine.transition(db, job_id, KBManagementState.PENDING.value)
            
            # 更新状态：开始解析
            await state_machine.transition(db, job_id, KBManagementState.PARSING.value)
            
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
            local_file_path = await upload_service.download_from_s3(s3_key)
            
            # 验证下载结果
            if not local_file_path:
                logger.error(f"文件下载失败，未返回本地文件路径: S3键={s3_key}")
                raise ValueError("文件下载失败，未返回本地文件路径")
            
            logger.debug(f"文件下载成功: {local_file_path}")
            
            # 准备解析参数 - 从S3键中提取文件名
            filename = os.path.basename(s3_key)
            
            # 调用修改后的解析逻辑（传入user_config）
            from app.services.knowledge.knowledge_base_service import checkerboard_inject_parse
            
            logger.debug(f"开始解析文件: {filename}, 类型: {job.job_metadata.get('doc_type', 'auto')}")
            
            add_dir = await checkerboard_inject_parse(
                file_full_path=local_file_path,
                filename=filename,
                user_config=user_config,  # 传入用户配置
                kb_dir=job.job_metadata.get("kb_dir", "默认目录"),
                doc_type=job.job_metadata.get("doc_type", "auto"),
                smart_title_parse=job.job_metadata.get("smart_title_parse", True),
                summary_image=job.job_metadata.get("summary_image", True),
                summary_table=job.job_metadata.get("summary_table", True),
                summary_txt=job.job_metadata.get("summary_txt", True),
                add_frag_desc=job.job_metadata.get("add_frag_desc", ""),
            )
            
            if not add_dir:
                logger.error(f"文件解析失败，未返回解析目录: {filename}")
                raise ValueError("文件解析失败，未返回解析目录")
            
            logger.info(f"文件解析成功: {add_dir}")
            
            # 更新状态：解析完成，开始向量化
            await state_machine.transition(db, job_id, KBManagementState.VECTORIZING.value)
            
            # 调用旧方案的向量化逻辑
            from app.services.knowledge.kb_encoder_service import encode_kb
            
            user_info = await encode_kb(user_config, add_dir=add_dir, mode="add")
            
            # 更新状态：向量化完成
            await state_machine.transition(
                db, job_id, KBManagementState.VECTORIZED.value,
                {"add_dir": add_dir, "user_info": user_info}
            )
            
            # 清理临时文件
            try:
                if os.path.exists(local_file_path):
                    os.remove(local_file_path)
            except Exception as e:
                logger.warning(f"清理临时文件失败: {e}")
            
            return {
                "status": "success",
                "job_id": job_id,
                "add_dir": add_dir,
                "vectors_count": len(user_info.get("all_vec", [])),
                "contents_count": len(user_info.get("all_contents_df", []))
            }
            
    except Exception as e:
        logger.error(f"解析并向量化失败: {e}")
        async with get_db_context() as db:
            await state_machine.mark_failed(db, job_id, str(e))
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
    """异步存储到数据库"""
    state_machine = JobStateMachine()
    job_repo = JobRepository()
    
    try:
        # 从上一个任务的结果中获取job_id
        job_id = prev_result.get("job_id")
        if not job_id:
            raise ValueError("缺少job_id参数")
            
        async with get_db_context() as db:
            # 获取Job
            job = await job_repo.get_job_by_id(db, job_id)
            if not job:
                raise ValueError("Job不存在")
            
            # 从job_metadata获取用户配置，如缺失则回退到Redis
            user_config = (job.job_metadata or {}).get("user_config") if job.job_metadata else None
            if not user_config:
                from app.services.redis import RedisServiceFactory
                from app.services.redis.user_redis_service import UserRedisService
                from app.services.user.user_config_service import UserConfigService

                redis_service = RedisServiceFactory.get_service()
                user_redis_service = UserRedisService(redis_service)
                user_config = await user_redis_service.get_user_config(job.user_id)

                if not user_config:
                    logger.warning(f"Job {job_id} metadata缺少用户配置，尝试重新初始化用户配置")
                    user_config_str = UserConfigService.init_user(str(job.user_id))
                    user_config = json.loads(user_config_str)
                    await user_redis_service.save_user_config(job.user_id, user_config)

                if not user_config:
                    raise ValueError("Job中缺少用户配置")

                metadata_update = dict(job.job_metadata or {})
                metadata_update["user_config"] = make_json_safe(user_config)
                job.job_metadata = metadata_update
                await db.commit()
                await db.refresh(job)
            
            # 更新状态：向量化完成，开始存储数据库
            await state_machine.transition(db, job_id, KBManagementState.VECTORIZED.value)
            await state_machine.transition(db, job_id, KBManagementState.STORING_DB.value)
            
            # 从全局管理器获取向量化结果
            from app.services.common.global_manager_service import global_df_manager
            user_key = f"{user_config['user']}_all_contents_df"
            all_contents_df = global_df_manager.get_dataframe(user_key)
            logger.debug(f"user_key: {user_key}, all_contents_df length: {len(all_contents_df)}")
            
            kb_records = []
            if all_contents_df is not None and len(all_contents_df) > 0:
                # 存储到数据库（knowledge_base表）
                from app.repositories.knowledge_base_repository import create_update_kb
                from app.models.database.knowledge_base import KBPydantic
                
                # 转换DataFrame为数据库记录（只存新增的内容）
                contents_count = len(all_contents_df)
                for _, row in all_contents_df.tail(contents_count).iterrows():
                    logger.debug(f"row: {row}")
                    kb_record = KBPydantic(
                        content=row.get('content'),
                        path=row.get('path'),
                        type=row.get('type'),
                        length=row.get('length'),
                        keywords=row.get('keywords'),
                        summary=row.get('summary'),
                        know_id=row.get('know_id'),
                        tokens=row.get('tokens'),
                        embedding=None  # 向量存储在文件系统
                    )
                    kb_records.append(kb_record)
                
                # 批量插入数据库
                if kb_records:
                    await create_update_kb(kb_records)
            
            job_metadata = job.job_metadata or {}

            source_file_name = job_metadata.get("source_file_name") or job.file_path or job_metadata.get("source_url")
            if isinstance(source_file_name, str) and "/" in source_file_name:
                source_file_name = os.path.basename(source_file_name)

            result_payload = {
                "document_metadata": {
                    "source_file_name": source_file_name,
                    "total_chunks": 0
                },
                "chunks": []
            }

            recent_df = None
            if all_contents_df is not None and len(all_contents_df) > 0:
                contents_count = len(all_contents_df)
                recent_df = all_contents_df.tail(contents_count)

            if recent_df is not None and len(recent_df) > 0:
                chunks = []

                def _sanitize(value):
                    if value is None:
                        return None
                    try:
                        if value != value:  # NaN
                            return None
                    except Exception:
                        pass
                    return value

                for index, (_, row) in enumerate(recent_df.iterrows()):
                    raw_type = str(row.get("type") or "").lower()
                    if "table" in raw_type:
                        chunk_type = "table"
                    elif "image" in raw_type:
                        chunk_type = "image"
                    elif "summary" in raw_type:
                        chunk_type = "summary"
                    elif "title" in raw_type:
                        chunk_type = "title"
                    else:
                        chunk_type = "paragraph"

                    keywords = row.get("keywords")
                    if isinstance(keywords, str):
                        try:
                            keywords_list = json.loads(keywords)
                            if not isinstance(keywords_list, list):
                                keywords_list = [keywords]
                        except json.JSONDecodeError:
                            keywords_list = [kw.strip() for kw in keywords.split(",") if kw.strip()]
                    elif isinstance(keywords, list):
                        keywords_list = keywords
                    else:
                        keywords_list = []

                    chunk_id = row.get("know_id") or str(uuid.uuid4())
                    chunk_text = row.get("content") or ""
                    chunk_summary = row.get("summary") or ""
                    chunk_length = row.get("length")
                    chunk_path = _sanitize(row.get("path"))
                    if chunk_length is None and chunk_text:
                        chunk_length = len(chunk_text)

                    tokens = row.get("tokens")
                    if isinstance(tokens, str) and tokens.isdigit():
                        tokens = int(tokens)
                    elif tokens is None:
                        tokens = 0

                    chunks.append({
                        "chunk_id": str(chunk_id),
                        "text": chunk_text,
                        "type": chunk_type,
                        "metadata": {
                            "path": chunk_path,
                            "length": int(chunk_length) if chunk_length is not None else len(chunk_text),
                            "tokens": tokens if isinstance(tokens, int) else 0,
                            "keywords": keywords_list,
                            "summary": chunk_summary or "",
                            "relationships": []
                        },
                        "order": index
                    })

                result_payload["document_metadata"]["total_chunks"] = len(chunks)
                result_payload["chunks"] = chunks

            # 处理 result_mode 逻辑
            requested_mode = job_metadata.get("result_mode", "auto")
            inline_threshold = getattr(settings, "RESULT_INLINE_THRESHOLD", 3 * 1024 * 1024)
            result_json_bytes = json.dumps(result_payload, ensure_ascii=False).encode("utf-8")

            if requested_mode == "auto":
                delivery_mode = "inline" if len(result_json_bytes) <= inline_threshold else "url"
            else:
                delivery_mode = requested_mode

            upload_service = FileUploadService()
            job_result_repo = JobResultRepository()
            result_s3_key = None
            inline_payload = None
            if delivery_mode == "inline":
                inline_payload = result_payload
                result_size = len(result_json_bytes)
            else:
                result_s3_key = await upload_service.upload_json_result(job_id, result_payload)
                result_size = len(result_json_bytes)

            job_result = await job_result_repo.upsert_job_result(
                db,
                job_id=job_id,
                delivery_mode=delivery_mode,
                document_metadata=result_payload.get("document_metadata"),
                inline_payload=inline_payload,
                result_s3_key=result_s3_key,
                result_size=result_size
            )

            await job_result_repo.replace_chunks(db, job_result.id, result_payload.get("chunks", []))

            metadata_update = dict(job_metadata)
            metadata_update["result_mode"] = delivery_mode
            metadata_update.pop("result", None)
            job.job_metadata = metadata_update
            await db.commit()

            # 更新状态：数据库存储完成，标记任务为completed
            await state_machine.transition(db, job_id, KBManagementState.DB_STORED.value)
            await state_machine.mark_completed(db, job_id, {
                "storage_completed": True,
                "stored_count": len(kb_records),
                "delivery_mode": delivery_mode
            })

            logger.info(f"知识库存储完成: job_id={job_id}, stored_count={len(kb_records)}")

            return {
                "status": "success",
                "job_id": job_id,
                "stored_count": len(kb_records),
                "delivery_mode": delivery_mode,
                "result_s3_key": result_s3_key
            }
            
    except Exception as e:
        logger.error(f"存储数据库失败: {e}")
        async with get_db_context() as db:
            await state_machine.mark_failed(db, job_id, str(e))
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
            
            # 检查是否需要发送Webhook
            if not job.webhook_enabled or not job.webhook_url:
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
                "delivery_mode": job_result.delivery_mode,
                "document_metadata": job_result.document_metadata or {},
                "completed_at": datetime.utcnow().isoformat()
            }

            if job_result.delivery_mode == "inline" and job_result.inline_payload:
                webhook_payload["result"] = job_result.inline_payload
            elif job_result.delivery_mode == "url" and job_result.result_s3_key:
                webhook_payload["result_url"] = await upload_service.generate_download_url(job_result.result_s3_key)

            webhook_result = await webhook_service.send_webhook(
                job_id=job_id,
                webhook_url=job.webhook_url,
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
