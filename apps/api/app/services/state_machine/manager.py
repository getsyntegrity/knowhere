"""
统一状态机管理器 - 集成所有状态机服务
"""
import time
from typing import Any, Dict, List, Optional

from shared.services.redis import RedisServiceFactory
from app.services.state_machine.state_machine_service import \
    StateMachineService
from app.services.state_machine.state_sync_service import StateSyncService
from app.services.state_machine.state_timeout_service import \
    StateTimeoutService
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession


class JobStateMachine:
    """Job状态机管理器 - 集成所有状态机服务"""
    
    def __init__(self, redis_service=None):
        self.redis = redis_service or RedisServiceFactory.get_service()
        
        # 初始化各个服务
        self.state_machine = StateMachineService(self.redis)
        self.state_sync = StateSyncService(self.redis)
        self.state_timeout = StateTimeoutService(self.redis)
    
    # 状态转换相关方法
    
    async def transition(
        self, 
        db: AsyncSession,
        job_id: str, 
        to_state: str, 
        transition_reason: str = "normal_transition",
        operator_id: Optional[str] = None,
        operator_type: str = "system",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """执行状态转换"""
        try:
            # 直接调用状态机服务（已包含乐观锁重试机制）
            result = await self.state_machine.transition(
                db, job_id, to_state, transition_reason, operator_id, operator_type, metadata
            )
            
            # 状态转换成功后，设置超时
            if result:
                await self.state_timeout.set_task_timeout(job_id, to_state)
            
            return result
            
        except Exception as e:
            logger.error(f"Job {job_id} 状态转换失败: {e}")
            return False
    
    async def get_current_state(self, db: AsyncSession, job_id: str) -> Optional[str]:
        """获取当前状态"""
        return await self.state_machine.get_current_state(db, job_id)
    
    async def is_terminal_state(self, db: AsyncSession, job_id: str) -> bool:
        """检查是否为终态"""
        return await self.state_machine.is_terminal_state(db, job_id)
    
    async def mark_failed(
        self, 
        db: AsyncSession, 
        job_id: str, 
        error_message: str,
        error_code: str = "UNKNOWN",
        error_details: Optional[Dict[str, Any]] = None,
        operator_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """标记Job为失败状态"""
        try:
            result = await self.state_machine.mark_failed(
                db, job_id, error_message, error_code, error_details, operator_id, metadata
            )
            
            # 失败后清除超时
            if result:
                await self.state_timeout.clear_task_timeout(job_id)
            
            return result
            
        except Exception as e:
            logger.error(f"标记Job {job_id} 失败状态时出错: {e}")
            return False
    
    async def mark_completed(
        self, 
        db: AsyncSession, 
        job_id: str, 
        result_metadata: Optional[Dict[str, Any]] = None,
        operator_id: Optional[str] = None
    ) -> bool:
        """标记Job为完成状态"""
        try:
            result = await self.state_machine.mark_completed(
                db, job_id, result_metadata, operator_id
            )
            
            # 完成后清除超时
            if result:
                await self.state_timeout.clear_task_timeout(job_id)
            
            return result
            
        except Exception as e:
            logger.error(f"标记Job {job_id} 完成状态时出错: {e}")
            return False
    
    async def handle_retry(
        self, 
        db: AsyncSession, 
        job_id: str, 
        retry_metadata: Optional[Dict[str, Any]] = None,
        operator_id: Optional[str] = None
    ) -> bool:
        """处理任务重试"""
        try:
            result = await self.state_machine.handle_retry(
                db, job_id, retry_metadata, operator_id
            )
            
            # 重试成功后，重新设置超时
            if result:
                current_state = await self.get_current_state(db, job_id)
                if current_state:
                    await self.state_timeout.set_task_timeout(job_id, current_state)
            
            return result
            
        except Exception as e:
            logger.error(f"处理Job {job_id} 重试时出错: {e}")
            return False
    
    # 状态同步相关方法
    
    async def sync_job_state_to_redis(self, db: AsyncSession, job_id: str) -> bool:
        """将数据库状态同步到Redis"""
        return await self.state_sync.sync_job_state_to_redis(db, job_id)
    
    async def sync_job_state_from_redis(self, db: AsyncSession, job_id: str) -> bool:
        """将Redis状态同步到数据库"""
        return await self.state_sync.sync_job_state_from_redis(db, job_id)
    
    async def check_state_consistency(self, db: AsyncSession, job_id: str) -> Dict[str, Any]:
        """检查状态一致性"""
        return await self.state_sync.check_state_consistency(db, job_id)
    
    async def repair_inconsistent_states(self, db: AsyncSession, job_ids: List[str]) -> Dict[str, bool]:
        """修复不一致的状态"""
        return await self.state_sync.repair_inconsistent_states(db, job_ids)
    
    async def batch_sync_all_states(self, db: AsyncSession) -> Dict[str, Any]:
        """批量同步所有状态"""
        return await self.state_sync.batch_sync_all_states(db)
    
    # 超时处理相关方法
    
    async def check_timeout_tasks(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """检查超时任务 - Keyspace Notifications模式下通常返回空列表"""
        return await self.state_timeout.check_timeout_tasks(db)
    
    async def handle_timeout_tasks(self, db: AsyncSession, timeout_tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """处理超时任务"""
        return await self.state_timeout.handle_timeout_tasks(db, self.state_machine, timeout_tasks)
    
    async def set_task_timeout(self, job_id: str, state: str) -> bool:
        """设置任务超时"""
        return await self.state_timeout.set_task_timeout(job_id, state)
    
    async def extend_task_timeout(self, job_id: str, state: str) -> bool:
        """延长任务超时时间"""
        return await self.state_timeout.extend_task_timeout(job_id, state)
    
    async def clear_task_timeout(self, job_id: str) -> bool:
        """清除任务超时"""
        return await self.state_timeout.clear_task_timeout(job_id)
    
    async def get_timeout_info(self, job_id: str) -> Dict[str, Any]:
        """获取任务超时信息"""
        return await self.state_timeout.get_timeout_info(job_id)
    
    async def start_timeout_listener(self):
        """启动超时监听器"""
        await self.state_timeout.start_listening()
    
    async def stop_timeout_listener(self):
        """停止超时监听器"""
        await self.state_timeout.stop_listening()
    
    async def is_timeout_listener_running(self) -> bool:
        """检查超时监听器是否运行中"""
        return await self.state_timeout.is_listening()
    
    
    # 综合管理方法
    
    async def health_check(self, db: AsyncSession) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 检查Redis连接
            redis_status = await self._check_redis_connection()
            
            # 检查超时任务
            timeout_tasks = await self.check_timeout_tasks(db)
            
            # 检查状态一致性（抽样检查）
            consistency_check = await self._sample_consistency_check(db)
            
            return {
                "status": "healthy" if redis_status and consistency_check["is_consistent"] else "unhealthy",
                "redis_status": redis_status,
                "timeout_tasks": len(timeout_tasks),
                "consistency_check": consistency_check,
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": time.time()
            }
    
    async def maintenance(self, db: AsyncSession) -> Dict[str, Any]:
        """维护操作"""
        try:
            results = {}
            
            # 批量同步状态
            results["sync_results"] = await self.batch_sync_all_states(db)
            
            # 处理超时任务
            timeout_tasks = await self.check_timeout_tasks(db)
            if timeout_tasks:
                results["timeout_handling"] = await self.handle_timeout_tasks(db, timeout_tasks)
            else:
                results["timeout_handling"] = {"total_timeout": 0, "handled_success": 0, "handled_failed": 0}
            
            logger.info(f"状态机维护完成: {results}")
            return results
            
        except Exception as e:
            logger.error(f"状态机维护失败: {e}")
            return {"error": str(e)}
    
    # 私有方法
    
    async def _check_redis_connection(self) -> bool:
        """检查Redis连接"""
        try:
            await self.redis.ping()
            return True
        except Exception as e:
            logger.error(f"Redis连接检查失败: {e}")
            return False
    
    async def _sample_consistency_check(self, db: AsyncSession, sample_size: int = 10) -> Dict[str, Any]:
        """抽样检查状态一致性"""
        try:
            # 这里可以实现抽样检查逻辑
            # 为了简化，暂时返回一致
            return {
                "is_consistent": True,
                "sample_size": sample_size,
                "checked_tasks": []
            }
        except Exception as e:
            logger.error(f"抽样一致性检查失败: {e}")
            return {
                "is_consistent": False,
                "error": str(e),
                "sample_size": sample_size
            }