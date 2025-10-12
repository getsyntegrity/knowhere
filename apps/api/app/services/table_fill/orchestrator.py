"""
表格填充编排服务
"""
from typing import Optional
from celery import chain
from loguru import logger

from app.core.tasks.table_fill_tasks import (
    upload_file_task,
    extract_table_task,
    kb_search_task,
    llm_process_task,
    fill_table_task,
    generate_result_task
)
from app.core.state_machine import TableFillState
from app.core.celery_router import task_router


class TableFillOrchestrator:
    """表格填充编排器"""
    
    def __init__(self):
        self.task_router = task_router
    
    async def start_workflow(
        self,
        db,
        job_id: str,
        source_type: str,
        file_path: Optional[str] = None,
        file_url: Optional[str] = None,
        user_id: str = None
    ) -> str:
        """
        启动表格填充工作流
        
        Args:
            db: 数据库会话
            job_id: 任务ID
            source_type: 文件来源类型
            file_path: 文件路径（直传时使用）
            file_url: 文件URL（URL外链时使用）
            user_id: 用户ID
            
        Returns:
            str: 工作流ID
        """
        try:
            # 如果source_type是file_upload，将其映射为direct_upload以兼容现有逻辑
            if source_type == "file_upload":
                source_type = "direct_upload"
            
            # 如果source_type是url但没有提供file_url，尝试从job_metadata中获取
            if source_type == "url" and not file_url:
                from app.repositories.job_repository import JobRepository
                job_repo = JobRepository()
                job = await job_repo.get_job_by_id(db, job_id)
                if job and job.job_metadata and "file_url" in job.job_metadata:
                    file_url = job.job_metadata["file_url"]
            
            # 获取队列名称
            queue_name = self.task_router.get_queue_for_job("table_fill", user_id)
            
            # 构建任务链
            workflow = chain(
                # 步骤1: 上传文件
                upload_file_task.s(
                    job_id=job_id,
                    source_type=source_type,
                    file_path=file_path,
                    file_url=file_url,
                    user_id=user_id,
                    job_type="table_fill"
                ).set(queue=queue_name),
                
                # 步骤2: 提取表格
                extract_table_task.s(
                    user_id=user_id,
                    job_type="table_fill"
                ).set(queue=queue_name),
                
                # 步骤3: 知识库检索
                kb_search_task.s(
                    user_id=user_id,
                    job_type="table_fill"
                ).set(queue=queue_name),
                
                # 步骤4: LLM处理
                llm_process_task.s(
                    user_id=user_id,
                    job_type="table_fill"
                ).set(queue=queue_name),
                
                # 步骤5: 填充表格
                fill_table_task.s(
                    user_id=user_id,
                    job_type="table_fill"
                ).set(queue=queue_name),
                
                # 步骤6: 生成结果
                generate_result_task.s(
                    user_id=user_id,
                    job_type="table_fill"
                ).set(queue=queue_name)
            )
            
            # 启动工作流
            result = workflow.apply_async()
            
            logger.info(f"表格填充工作流已启动: job_id={job_id}, workflow_id={result.id}, queue={queue_name}")
            
            return result.id
            
        except Exception as e:
            logger.error(f"启动表格填充工作流失败: {e}")
            raise
    
    def create_workflow_chain(self, job_id: str, user_id: str, queue_name: str = None):
        """
        创建表格填充工作流链（用于测试或手动执行）
        
        Args:
            job_id: 任务ID
            user_id: 用户ID
            queue_name: 队列名称（可选）
            
        Returns:
            chain: Celery任务链
        """
        if not queue_name:
            queue_name = self.task_router.get_queue_for_job("table_fill", user_id)
        
        return chain(
            upload_file_task.s(
                job_id=job_id,
                user_id=user_id,
                job_type="table_fill"
            ).set(queue=queue_name),
            
            extract_table_task.s(
                job_id=job_id,
                user_id=user_id,
                job_type="table_fill"
            ).set(queue=queue_name),
            
            kb_search_task.s(
                job_id=job_id,
                user_id=user_id,
                job_type="table_fill"
            ).set(queue=queue_name),
            
            llm_process_task.s(
                job_id=job_id,
                user_id=user_id,
                job_type="table_fill"
            ).set(queue=queue_name),
            
            fill_table_task.s(
                job_id=job_id,
                user_id=user_id,
                job_type="table_fill"
            ).set(queue=queue_name),
            
            generate_result_task.s(
                job_id=job_id,
                user_id=user_id,
                job_type="table_fill"
            ).set(queue=queue_name)
        )
    
    def get_workflow_status(self, workflow_id: str) -> dict:
        """
        获取工作流状态
        
        Args:
            workflow_id: 工作流ID
            
        Returns:
            dict: 工作流状态信息
        """
        try:
            from app.core.celery_app import get_celery_app
            celery_app = get_celery_app()
            
            result = celery_app.AsyncResult(workflow_id)
            
            return {
                "workflow_id": workflow_id,
                "status": result.state,
                "result": result.result if result.state == 'SUCCESS' else None,
                "error": str(result.info) if result.state == 'FAILURE' else None
            }
            
        except Exception as e:
            logger.error(f"获取工作流状态失败: {e}")
            return {
                "workflow_id": workflow_id,
                "status": "UNKNOWN",
                "error": str(e)
            }
    
    def cancel_workflow(self, workflow_id: str) -> bool:
        """
        取消工作流
        
        Args:
            workflow_id: 工作流ID
            
        Returns:
            bool: 是否成功取消
        """
        try:
            from app.core.celery_app import get_celery_app
            celery_app = get_celery_app()
            
            result = celery_app.AsyncResult(workflow_id)
            result.revoke(terminate=True)
            
            logger.info(f"工作流已取消: {workflow_id}")
            return True
            
        except Exception as e:
            logger.error(f"取消工作流失败: {e}")
            return False
