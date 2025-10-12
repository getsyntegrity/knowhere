"""
任务管理服务
"""

from typing import Dict, Any, Optional, List
from ..client import KnowhereClient
from ..types import JobStatusResponse, JobResultResponse


class JobManagementService:
    """任务管理服务"""
    
    def __init__(self, client: KnowhereClient):
        self.client = client
    
    async def get_job_status(self, job_id: str) -> JobStatusResponse:
        """
        获取任务状态
        
        Args:
            job_id: 任务ID
            
        Returns:
            JobStatusResponse: 任务状态
        """
        response = await self.client._request(
            "GET",
            f"/v1/jobs/{job_id}/status"
        )
        
        return JobStatusResponse(**response.data)
    
    async def get_job_result(self, job_id: str) -> JobResultResponse:
        """
        获取任务结果
        
        Args:
            job_id: 任务ID
            
        Returns:
            JobResultResponse: 任务结果
        """
        response = await self.client._request(
            "GET",
            f"/v1/jobs/{job_id}/result"
        )
        
        return JobResultResponse(**response.data)
    
    async def cancel_job(self, job_id: str) -> bool:
        """
        取消任务
        
        Args:
            job_id: 任务ID
            
        Returns:
            bool: 取消是否成功
        """
        try:
            await self.client._request(
                "POST",
                f"/v1/jobs/{job_id}/cancel"
            )
            return True
        except Exception:
            return False
    
    async def get_user_jobs(
        self,
        job_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[JobStatusResponse]:
        """
        获取用户的所有任务
        
        Args:
            job_type: 任务类型过滤（可选）
            status: 状态过滤（可选）
            limit: 返回数量限制
            offset: 偏移量
            
        Returns:
            List[JobStatusResponse]: 任务列表
        """
        params = {
            "limit": limit,
            "offset": offset
        }
        if job_type:
            params["job_type"] = job_type
        if status:
            params["status"] = status
        
        response = await self.client._request(
            "GET",
            "/v1/jobs",
            params=params
        )
        
        return [JobStatusResponse(**job) for job in response.data]
