"""
知识库管理Celery任务
"""
import asyncio
import json
import os
from typing import Dict, Any, Optional
from celery import Task
from loguru import logger

from app.core.celery_app import get_celery_app
from app.core.state_machine import JobStateMachine, KBManagementState
from app.repositories.job_repository import JobRepository
from app.services.storage.file_upload_service import FileUploadService
from app.core.database import get_db_context

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
                    loop.close()
        except Exception as e:
            logger.error(f"处理重试状态时出错: {e}")


@celery_app.task(bind=True, base=KBBaseTask, name='app.core.tasks.kb_tasks.upload_file_task')
def upload_file_task(self, job_id: str, source_type: str, file_path: Optional[str] = None, file_url: Optional[str] = None, user_id: str = None, job_type: str = "kb_management"):
    """上传文件任务"""
    try:
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
            result = loop.run_until_complete(_upload_file_async(
                job_id, source_type, file_path, file_url, user_id
            ))
            return result
        finally:
            # 只有在创建了新循环时才关闭
            if loop != asyncio.get_event_loop():
                loop.close()
            
    except Exception as e:
        logger.error(f"上传文件任务失败: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)


async def _upload_file_async(job_id: str, source_type: str, file_path: Optional[str], file_url: Optional[str], user_id: str):
    """异步上传文件"""
    state_machine = JobStateMachine()
    job_repo = JobRepository()
    upload_service = FileUploadService()
    
    try:
        # 更新状态：开始上传
        async with get_db_context() as db:
            await state_machine.transition(db, job_id, KBManagementState.UPLOADING.value)
            
            # 执行上传
            if source_type == "direct_upload":
                s3_key = await upload_service.handle_direct_upload(file_path, job_id)
            elif source_type == "url":
                s3_key = await upload_service.handle_url_upload(file_url, job_id)
            else:
                raise ValueError(f"不支持的文件来源类型: {source_type}")
            
            # 更新Job的S3键
            await job_repo.update_job_s3_key(db, job_id, s3_key)
            
            # 更新状态：上传完成
            await state_machine.transition(db, job_id, KBManagementState.UPLOADED.value)
            
            return {"status": "success", "s3_key": s3_key, "job_id": job_id}
            
    except Exception as e:
        logger.error(f"上传文件失败: {e}")
        async with get_db_context() as db:
            await state_machine.mark_failed(db, job_id, str(e))
        raise


@celery_app.task(bind=True, base=KBBaseTask, name='app.core.tasks.kb_tasks.parse_and_vectorize_task')
def parse_and_vectorize_task(self, upload_result: Dict[str, Any], user_id: str = None, job_type: str = "kb_management"):
    """解析并向量化任务（合并原步骤2-4）"""
    try:
        # 从上传结果中获取job_id
        job_id = upload_result.get('job_id')
        if not job_id:
            raise ValueError("上传结果中缺少job_id")
        
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
                job_id, upload_result, user_id
            ))
            return result
        finally:
            # 只有在创建了新循环时才关闭
            if loop != asyncio.get_event_loop():
                loop.close()
            
    except Exception as e:
        logger.error(f"解析并向量化任务失败: {e}")
        raise self.retry(exc=e, countdown=120, max_retries=2)


async def _parse_and_vectorize_async(job_id: str, upload_result: Dict[str, Any], user_id: str):
    """异步解析并向量化"""
    state_machine = JobStateMachine()
    job_repo = JobRepository()
    
    try:
        async with get_db_context() as db:
            # 获取Job和用户配置
            job = await job_repo.get_job_by_id(db, job_id)
            if not job or not job.job_metadata:
                raise ValueError("Job或用户配置不存在")
            
            user_config = job.job_metadata.get("user_config")
            if not user_config:
                raise ValueError("用户配置为空")
            
            # 更新状态：开始解析
            await state_machine.transition(db, job_id, KBManagementState.PARSING.value)
            
            # 获取S3键和文件信息
            s3_key = upload_result.get("s3_key") or job.s3_key
            file_path = upload_result.get("file_path") or job.file_path
            
            # 下载文件到本地临时目录
            from app.services.storage.file_upload_service import FileUploadService
            upload_service = FileUploadService()
            local_file_path = await upload_service.download_from_s3(s3_key)
            
            # 准备解析参数
            filename = os.path.basename(file_path)
            
            # 调用修改后的解析逻辑（传入user_config）
            from app.services.knowledge.knowledge_base_service import checkerboard_inject_parse
            
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
def store_to_db_task(self, vectorize_result: Dict[str, Any], user_id: str = None, job_type: str = "kb_management"):
    """存储到数据库任务"""
    try:
        # 从向量化结果中获取job_id
        job_id = vectorize_result.get('job_id')
        if not job_id:
            raise ValueError("向量化结果中缺少job_id")
        
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
                job_id, vectorize_result, user_id
            ))
            return result
        finally:
            # 只有在创建了新循环时才关闭
            if loop != asyncio.get_event_loop():
                loop.close()
            
    except Exception as e:
        logger.error(f"存储数据库任务失败: {e}")
        raise self.retry(exc=e, countdown=120, max_retries=2)


async def _store_to_db_async(job_id: str, vectorize_result: Dict[str, Any], user_id: str):
    """异步存储到数据库"""
    state_machine = JobStateMachine()
    job_repo = JobRepository()
    
    try:
        async with get_db_context() as db:
            # 获取Job
            job = await job_repo.get_job_by_id(db, job_id)
            if not job:
                raise ValueError("Job不存在")
            
            user_config = job.job_metadata.get("user_config")
            
            # 更新状态：向量化完成，开始存储数据库
            await state_machine.transition(db, job_id, KBManagementState.VECTORIZED.value)
            await state_machine.transition(db, job_id, KBManagementState.STORING_DB.value)
            
            # 从全局管理器获取向量化结果
            from app.services.common.global_manager_service import global_df_manager
            user_key = f"{user_config['user']}_all_contents_df"
            all_contents_df = global_df_manager.get_dataframe(user_key)
            
            kb_records = []
            if all_contents_df is not None and len(all_contents_df) > 0:
                # 存储到数据库（knowledge_base表）
                from app.repositories.knowledge_base_repository import create_update_kb
                from app.models.database.knowledge_base import KBPydantic
                
                # 转换DataFrame为数据库记录（只存新增的内容）
                contents_count = vectorize_result.get("contents_count", 10)
                for _, row in all_contents_df.tail(contents_count).iterrows():
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
            
            # 更新状态：数据库存储完成，标记任务为completed
            await state_machine.transition(db, job_id, KBManagementState.DB_STORED.value)
            await state_machine.mark_completed(db, job_id, {
                "vectorize_result": vectorize_result,
                "storage_completed": True,
                "stored_count": len(kb_records)
            })
            
            logger.info(f"知识库存储完成: job_id={job_id}, stored_count={len(kb_records)}")
            
            return {
                "status": "success",
                "job_id": job_id,
                "stored_count": len(kb_records)
            }
            
    except Exception as e:
        logger.error(f"存储数据库失败: {e}")
        async with get_db_context() as db:
            await state_machine.mark_failed(db, job_id, str(e))
        raise




@celery_app.task(bind=True, base=KBBaseTask, name='app.core.tasks.kb_tasks.send_webhook_task')
def send_webhook_task(self, store_result: Dict[str, Any], user_id: str = None, job_type: str = "kb_management"):
    """发送Webhook任务（独立步骤，失败不影响主任务）"""
    try:
        # 从存储结果中获取job_id
        job_id = store_result.get('job_id')
        if not job_id:
            raise ValueError("存储结果中缺少job_id")
        
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
            result = loop.run_until_complete(_send_webhook_async(job_id, store_result, user_id))
            return result
        finally:
            # 只有在创建了新循环时才关闭
            if loop != asyncio.get_event_loop():
                loop.close()
            
    except Exception as e:
        logger.error(f"发送Webhook任务失败（第{self.request.retries + 1}次）: {e}")
        # 独立重试机制：最多5次，间隔递增（60s, 120s, 240s, 480s, 960s）
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries), max_retries=5)


async def _send_webhook_async(job_id: str, store_result: Dict[str, Any], user_id: str):
    """异步发送Webhook"""
    job_repo = JobRepository()
    
    try:
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
            
            # 调用Webhook服务
            from app.services.webhook.webhook_service import WebhookService
            from datetime import datetime
            webhook_service = WebhookService()
            
            webhook_payload = {
                "job_id": job_id,
                "status": "completed",
                "result": {
                    "stored_count": store_result.get("stored_count", 0),
                    "completed_at": datetime.utcnow().isoformat()
                }
            }
            
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
        
        # 获取Job信息
        job_repo = JobRepository()
        job = await job_repo.get_job_by_id(db, job_id)
        
        if job and job.webhook_enabled:
            # 生成下载链接（如果有结果文件）
            download_url = None
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
