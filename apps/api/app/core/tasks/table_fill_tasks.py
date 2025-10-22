"""
表格填充Celery任务
"""
import asyncio
import os
from typing import Dict, Any, Optional
from celery import Task
from loguru import logger

from app.core.celery_app import get_celery_app
from app.core.state_machine import JobStateMachine, TableFillState
from app.repositories.job_repository import JobRepository
from app.repositories.job_result_repository import JobResultRepository
from app.services.storage.file_upload_service import FileUploadService
from app.core.database import get_db_context
from app.utils.json_utils import make_json_safe

# 获取Celery应用
celery_app = get_celery_app()


class TableFillBaseTask(Task):
    """表格填充基础任务类"""
    
    def on_success(self, retval, task_id, args, kwargs):
        """任务成功回调"""
        logger.info(f"表格填充任务 {task_id} 执行成功")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败回调"""
        logger.error(f"表格填充任务 {task_id} 执行失败: {exc}")
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """任务重试回调"""
        logger.warning(f"表格填充任务 {task_id} 重试: {exc}")
        
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
                # 使用同步方式处理重试状态，避免事件循环冲突
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
                            # 检查当前状态，决定使用哪种重试方式
                            job = await state_machine._get_job(db, job_id)
                            if job and job.current_state == "failed":
                                # 失败后重试 - 重新启动整个工作流
                                await state_machine.handle_failed_retry(db, job_id, {
                                    "retry_count": self.request.retries,
                                    "error_message": str(exc)
                                })
                                
                                # 重新启动工作流
                                from app.services.table_fill.orchestrator import TableFillOrchestrator
                                orchestrator = TableFillOrchestrator()
                                await orchestrator.start_workflow(
                                    db=db,
                                    job_id=job_id,
                                    source_type=job.source_type,
                                    file_path=job.file_path,
                                    file_url=None,  # 需要从metadata获取
                                    user_id=str(job.user_id)
                                )
                            else:
                                # 普通重试
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


@celery_app.task(bind=True, base=TableFillBaseTask, name='app.core.tasks.table_fill_tasks.upload_file_task')
def upload_file_task(self, job_id: str, source_type: str, file_path: Optional[str] = None, file_url: Optional[str] = None, user_id: str = None, job_type: str = "table_fill"):
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
    job_result_repo = JobResultRepository()
    
    try:
        # 更新状态：开始上传
        async with get_db_context() as db:
            await state_machine.transition(db, job_id, TableFillState.UPLOADING.value)
            
            # 执行上传
            if source_type == "file":
                # 文件已通过S3直传，验证存在性
                job = await job_repo.get_job_by_id(db, job_id)
                if not job or not job.s3_key:
                    raise ValueError(f"Job {job_id} 缺少S3键信息")
                
                # 验证S3文件存在
                file_info = await upload_service.verify_s3_file_exists(job.s3_key)
                if not file_info.get("exists"):
                    raise ValueError(f"S3文件不存在: {job.s3_key}")
                
                s3_key = job.s3_key
                logger.info(f"文件已通过S3直传: {s3_key}")
                
            elif source_type == "url":
                s3_key = await upload_service.handle_url_upload(file_url, job_id)
                # 更新Job的S3键
                await job_repo.update_job_s3_key(db, job_id, s3_key)
            else:
                raise ValueError(f"不支持的文件来源类型: {source_type}")
            
            # 更新状态：上传完成
            await state_machine.transition(db, job_id, TableFillState.UPLOADED.value)
            
            return {"status": "success", "s3_key": s3_key, "job_id": job_id}
            
    except Exception as e:
        logger.error(f"上传文件失败: {e}")
        async with get_db_context() as db:
            await state_machine.mark_failed(db, job_id, str(e))
        raise


@celery_app.task(bind=True, base=TableFillBaseTask, name='app.core.tasks.table_fill_tasks.extract_table_task')
def extract_table_task(self, upload_result: Dict[str, Any], user_id: str = None, job_type: str = "table_fill"):
    """提取表格任务（TODO标注）"""
    try:
        # 从上传结果中获取job_id和s3_key
        job_id = upload_result.get('job_id')
        s3_key = upload_result.get('s3_key')
        if not job_id or not s3_key:
            raise ValueError("上传结果中缺少job_id或s3_key")
        
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
            result = loop.run_until_complete(_extract_table_async(job_id, s3_key, user_id))
            return result
        finally:
            # 只有在创建了新循环时才关闭
            if loop != asyncio.get_event_loop():
                loop.close()
            
    except Exception as e:
        logger.error(f"提取表格任务失败: {e}")
        raise self.retry(exc=e, countdown=120, max_retries=2)


async def _extract_table_async(job_id: str, s3_key: str, user_id: str):
    """异步提取表格"""
    state_machine = JobStateMachine()
    
    try:
        # 更新状态：开始提取表格
        async with get_db_context() as db:
            await state_machine.transition(db, job_id, TableFillState.EXTRACTING_TABLE.value)
            
            # TODO: 实际业务逻辑 - 提取表格
            # 这里应该实现：
            # 1. 从S3下载文件
            # 2. 使用表格提取算法（如pandas, openpyxl等）
            # 3. 识别表格结构
            # 4. 保存表格数据到临时存储
            
            # 模拟处理时间
            await asyncio.sleep(2)
            
            # 模拟提取结果
            table_data = {
                "tables": [
                    {
                        "sheet_name": "Sheet1",
                        "rows": 10,
                        "columns": 5,
                        "headers": ["列1", "列2", "列3", "列4", "列5"],
                        "data": [
                            ["值1", "值2", "值3", "值4", "值5"],
                            # ... 更多行数据
                        ]
                    }
                ]
            }
            
            # 更新状态：表格提取完成
            safe_table_data = make_json_safe(table_data)
            await state_machine.transition(
                db, job_id, TableFillState.TABLE_EXTRACTED.value,
                "table_extraction_completed", None, "system",
                {"table_data": safe_table_data}
            )
            
            return {"status": "success", "table_data": table_data, "job_id": job_id}
            
    except Exception as e:
        logger.error(f"提取表格失败: {e}")
        async with get_db_context() as db:
            await state_machine.mark_failed(db, job_id, str(e))
        raise


@celery_app.task(bind=True, base=TableFillBaseTask, name='app.core.tasks.table_fill_tasks.kb_search_task')
def kb_search_task(self, table_data: Dict[str, Any], user_id: str = None, job_type: str = "table_fill"):
    """知识库检索任务（TODO标注）"""
    try:
        # 从表格数据中获取job_id
        job_id = table_data.get('job_id')
        if not job_id:
            raise ValueError("表格数据中缺少job_id")
        
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
            result = loop.run_until_complete(_kb_search_async(job_id, table_data, user_id))
            return result
        finally:
            # 只有在创建了新循环时才关闭
            if loop != asyncio.get_event_loop():
                loop.close()
            
    except Exception as e:
        logger.error(f"知识库检索任务失败: {e}")
        raise self.retry(exc=e, countdown=120, max_retries=2)


async def _kb_search_async(job_id: str, table_data: Dict[str, Any], user_id: str):
    """异步知识库检索"""
    state_machine = JobStateMachine()
    
    try:
        # 更新状态：开始知识库检索
        async with get_db_context() as db:
            await state_machine.transition(db, job_id, TableFillState.KB_SEARCHING.value)
            
            # TODO: 实际业务逻辑 - 知识库检索
            # 这里应该实现：
            # 1. 遍历表格的每个字段
            # 2. 对每个字段进行知识库检索
            # 3. 使用现有的知识库检索服务
            # 4. 收集检索结果
            
            # 模拟处理时间
            await asyncio.sleep(3)
            
            # 模拟检索结果
            search_results = {
                "field_searches": [
                    {
                        "field_name": "列1",
                        "search_query": "列1相关查询",
                        "results": [
                            {"content": "相关知识点1", "score": 0.95},
                            {"content": "相关知识点2", "score": 0.87}
                        ]
                    },
                    # ... 更多字段检索结果
                ]
            }
            
            # 更新状态：知识库检索完成
            safe_search_results = make_json_safe(search_results)
            await state_machine.transition(
                db, job_id, TableFillState.KB_SEARCHED.value,
                "kb_search_completed", None, "system",
                {"search_results": safe_search_results}
            )
            
            return {"status": "success", "search_results": search_results, "job_id": job_id}
            
    except Exception as e:
        logger.error(f"知识库检索失败: {e}")
        async with get_db_context() as db:
            await state_machine.mark_failed(db, job_id, str(e))
        raise


@celery_app.task(bind=True, base=TableFillBaseTask, name='app.core.tasks.table_fill_tasks.llm_process_task')
def llm_process_task(self, search_results: Dict[str, Any], user_id: str = None, job_type: str = "table_fill"):
    """LLM处理任务（TODO标注）"""
    try:
        # 从搜索结果中获取job_id
        job_id = search_results.get('job_id')
        if not job_id:
            raise ValueError("搜索结果中缺少job_id")
        
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
            result = loop.run_until_complete(_llm_process_async(job_id, search_results, user_id))
            return result
        finally:
            # 只有在创建了新循环时才关闭
            if loop != asyncio.get_event_loop():
                loop.close()
            
    except Exception as e:
        logger.error(f"LLM处理任务失败: {e}")
        raise self.retry(exc=e, countdown=180, max_retries=2)


async def _llm_process_async(job_id: str, search_results: Dict[str, Any], user_id: str):
    """异步LLM处理"""
    state_machine = JobStateMachine()
    
    try:
        # 更新状态：开始LLM处理
        async with get_db_context() as db:
            await state_machine.transition(db, job_id, TableFillState.LLM_PROCESSING.value)
            
            # 从状态历史中获取table_data
            from app.repositories.job_repository import JobRepository
            job_repo = JobRepository()
            table_data = await job_repo.get_job_state_metadata(db, job_id, "table_extracted", "table_data")
            
            if not table_data:
                raise ValueError("无法获取表格数据，请确保表格提取步骤已完成")
            
            # TODO: 实际业务逻辑 - LLM处理
            # 这里应该实现：
            # 1. 整合表格数据和检索结果
            # 2. 构建LLM提示词
            # 3. 调用LLM API（如OpenAI, DeepSeek等）
            # 4. 处理LLM响应，生成填充建议
            
            # 模拟处理时间
            await asyncio.sleep(5)
            
            # 模拟LLM处理结果
            llm_results = {
                "fill_suggestions": [
                    {
                        "row_index": 0,
                        "column_index": 0,
                        "original_value": "值1",
                        "suggested_value": "增强后的值1",
                        "confidence": 0.92,
                        "reasoning": "基于知识库检索结果，建议使用更准确的表述"
                    },
                    # ... 更多填充建议
                ],
                "summary": "已为表格中的关键字段生成了基于知识库的填充建议"
            }
            
            # 更新状态：LLM处理完成
            safe_llm_results = make_json_safe(llm_results)
            await state_machine.transition(
                db, job_id, TableFillState.LLM_PROCESSED.value,
                "llm_processing_completed", None, "system",
                {"llm_results": safe_llm_results}
            )
            
            return {"status": "success", "llm_results": llm_results, "job_id": job_id}
            
    except Exception as e:
        logger.error(f"LLM处理失败: {e}")
        async with get_db_context() as db:
            await state_machine.mark_failed(db, job_id, str(e))
        raise


@celery_app.task(bind=True, base=TableFillBaseTask, name='app.core.tasks.table_fill_tasks.fill_table_task')
def fill_table_task(self, llm_results: Dict[str, Any], user_id: str = None, job_type: str = "table_fill"):
    """填充表格任务（TODO标注）"""
    try:
        # 从LLM结果中获取job_id
        job_id = llm_results.get('job_id')
        if not job_id:
            raise ValueError("LLM结果中缺少job_id")
        
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
            result = loop.run_until_complete(_fill_table_async(job_id, llm_results, user_id))
            return result
        finally:
            # 只有在创建了新循环时才关闭
            if loop != asyncio.get_event_loop():
                loop.close()
            
    except Exception as e:
        logger.error(f"填充表格任务失败: {e}")
        raise self.retry(exc=e, countdown=120, max_retries=2)


async def _fill_table_async(job_id: str, llm_results: Dict[str, Any], user_id: str):
    """异步填充表格"""
    state_machine = JobStateMachine()
    
    try:
        # 更新状态：开始填充表格
        async with get_db_context() as db:
            await state_machine.transition(db, job_id, TableFillState.FILLING_TABLE.value)
            
            # 从状态历史中获取table_data
            from app.repositories.job_repository import JobRepository
            job_repo = JobRepository()
            table_data = await job_repo.get_job_state_metadata(db, job_id, "table_extracted", "table_data")
            
            if not table_data:
                raise ValueError("无法获取表格数据，请确保表格提取步骤已完成")
            
            # TODO: 实际业务逻辑 - 填充表格
            # 这里应该实现：
            # 1. 根据LLM建议更新表格数据
            # 2. 应用填充规则
            # 3. 生成填充后的表格
            # 4. 保存到临时文件
            
            # 模拟处理时间
            await asyncio.sleep(2)
            
            # 模拟填充结果
            filled_table_data = {
                "original_tables": table_data["tables"],
                "filled_tables": [
                    {
                        "sheet_name": "Sheet1_Filled",
                        "rows": 10,
                        "columns": 5,
                        "headers": ["列1", "列2", "列3", "列4", "列5"],
                        "data": [
                            ["增强后的值1", "值2", "值3", "值4", "值5"],
                            # ... 填充后的数据
                        ]
                    }
                ],
                "fill_statistics": {
                    "total_cells": 50,
                    "filled_cells": 12,
                    "fill_rate": 0.24
                }
            }
            
            # 更新状态：表格填充完成
            safe_filled_table_data = make_json_safe(filled_table_data)
            await state_machine.transition(
                db, job_id, TableFillState.TABLE_FILLED.value,
                "table_filling_completed", None, "system",
                {"filled_table_data": safe_filled_table_data}
            )
            
            return {"status": "success", "filled_table_data": filled_table_data, "job_id": job_id}
            
    except Exception as e:
        logger.error(f"填充表格失败: {e}")
        async with get_db_context() as db:
            await state_machine.mark_failed(db, job_id, str(e))
        raise


@celery_app.task(bind=True, base=TableFillBaseTask, name='app.core.tasks.table_fill_tasks.generate_result_task')
def generate_result_task(self, filled_table_data: Dict[str, Any], user_id: str = None, job_type: str = "table_fill"):
    """生成结果任务"""
    try:
        # 从填充表格数据中获取job_id
        job_id = filled_table_data.get('job_id')
        if not job_id:
            raise ValueError("填充表格数据中缺少job_id")
        
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
            result = loop.run_until_complete(_generate_result_async(job_id, filled_table_data, user_id))
            return result
        finally:
            # 只有在创建了新循环时才关闭
            if loop != asyncio.get_event_loop():
                loop.close()
            
    except Exception as e:
        logger.error(f"生成结果任务失败: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=2)


async def _generate_result_async(job_id: str, filled_table_data: Dict[str, Any], user_id: str):
    """异步生成结果"""
    state_machine = JobStateMachine()
    job_repo = JobRepository()
    upload_service = FileUploadService()
    
    try:
        # 更新状态：开始生成结果
        async with get_db_context() as db:
            await state_machine.transition(db, job_id, TableFillState.GENERATING_RESULT.value)
            
            # 生成结果文件（Excel格式）
            import tempfile
            import pandas as pd
            
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp_file:
                # 创建Excel文件
                with pd.ExcelWriter(temp_file.name, engine='openpyxl') as writer:
                    for table in filled_table_data["filled_tables"]:
                        df = pd.DataFrame(table["data"], columns=table["headers"])
                        df.to_excel(writer, sheet_name=table["sheet_name"], index=False)
                
                # 上传到S3
                file_size = os.path.getsize(temp_file.name)
                result_s3_key = await upload_service.upload_result_file(
                    temp_file.name, job_id, ".xlsx"
                )
                
                # 清理临时文件
                import os
                os.unlink(temp_file.name)
            
            job_result = await job_result_repo.upsert_job_result(
                db,
                job_id=job_id,
                delivery_mode="url",
                document_metadata={
                    "file_type": "xlsx",
                    "filled_tables": len(filled_table_data.get("filled_tables", []))
                },
                result_s3_key=result_s3_key,
                result_size=file_size
            )
            await job_result_repo.replace_chunks(db, job_result.id, [])

            # 更新状态：任务完成
            result_metadata = {
                "result_s3_key": result_s3_key,
                "file_type": "xlsx",
                "fill_statistics": filled_table_data.get("fill_statistics", {}),
                "delivery_mode": "url"
            }
            await state_machine.mark_completed(db, job_id, result_metadata)

            # 发送任务完成邮件
            await _send_job_completion_email(db, job_id, "table_fill", result_s3_key)

            return {"status": "success", "result_s3_key": result_s3_key, "job_id": job_id, "delivery_mode": "url"}
            
    except Exception as e:
        logger.error(f"生成结果失败: {e}")
        async with get_db_context() as db:
            await state_machine.mark_failed(db, job_id, str(e))
        raise


async def _send_job_completion_email(db, job_id: str, job_type: str, result_s3_key: str):
    """发送任务完成邮件"""
    try:
        from app.services.email import EmailService
        from app.repositories.job_repository import JobRepository
        from app.services.storage.file_upload_service import FileUploadService
        
        # 获取Job信息
        job_repo = JobRepository()
        job = await job_repo.get_job_by_id(db, job_id)
        
        if job and job.webhook_enabled:
            # 生成下载链接
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
