"""
表格填充服务
"""

from typing import Dict, Any, Optional
from ..client import KnowhereClient
from ..types import TableFillJobCreate, TableFillJobResponse, TableFillJobStatus


class TableFillService:
    """表格填充服务"""
    
    def __init__(self, client: KnowhereClient):
        self.client = client
    
    async def create_job(
        self,
        file_url: str,
        webhook_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TableFillJobResponse:
        """
        创建表格填充任务
        
        Args:
            file_url: 表格文件URL
            webhook_url: Webhook通知URL（可选）
            metadata: 额外元数据（可选）
            
        Returns:
            TableFillJobResponse: 任务创建响应
        """
        data = {
            "file_url": file_url,
            "webhook_url": webhook_url,
            "metadata": metadata or {}
        }
        
        response = await self.client._request(
            "POST",
            "/v1/table-fill/jobs",
            data=data
        )
        
        return TableFillJobResponse(**response.data)
    
    async def get_job_status(self, job_id: str) -> TableFillJobStatus:
        """
        获取任务状态
        
        Args:
            job_id: 任务ID
            
        Returns:
            TableFillJobStatus: 任务状态
        """
        response = await self.client._request(
            "GET",
            f"/v1/table-fill/jobs/{job_id}"
        )
        
        return TableFillJobStatus(**response.data)
    
    async def download_result(self, job_id: str) -> bytes:
        """
        下载结果文件
        
        Args:
            job_id: 任务ID
            
        Returns:
            bytes: 结果文件内容
        """
        response = await self.client._request(
            "GET",
            f"/v1/table-fill/jobs/{job_id}/download"
        )
        
        return response.data
    
    async def wait_for_completion(
        self,
        job_id: str,
        timeout: int = 3600,
        poll_interval: int = 5
    ) -> TableFillJobStatus:
        """
        等待任务完成
        
        Args:
            job_id: 任务ID
            timeout: 超时时间（秒）
            poll_interval: 轮询间隔（秒）
            
        Returns:
            TableFillJobStatus: 最终任务状态
        """
        import asyncio
        import time
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = await self.get_job_status(job_id)
            
            if status.status in ['completed', 'failed']:
                return status
            
            await asyncio.sleep(poll_interval)
        
        raise TimeoutError(f"任务 {job_id} 在 {timeout} 秒内未完成")
