"""
状态机监控和统计服务
"""
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.models.database.job import Job
from app.models.database.job_state_audit_log import JobStateAuditLog
from app.services.redis import RedisServiceFactory
from loguru import logger
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class StateMachineMonitoringService:
    """状态机监控和统计服务"""
    
    def __init__(self, redis_service=None):
        self.redis = redis_service or RedisServiceFactory.get_service()
    
    async def get_state_statistics(self, db: AsyncSession, hours: int = 24) -> Dict[str, Any]:
        """获取状态统计信息"""
        try:
            # 计算时间范围
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=hours)
            
            # 查询状态分布
            state_distribution = await self._get_state_distribution(db, start_time, end_time)
            
            # 查询状态转换统计
            transition_stats = await self._get_transition_statistics(db, start_time, end_time)
            
            # 查询任务完成率
            completion_rate = await self._get_completion_rate(db, start_time, end_time)
            
            # 查询平均处理时间
            avg_processing_time = await self._get_average_processing_time(db, start_time, end_time)
            
            return {
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "hours": hours
                },
                "state_distribution": state_distribution,
                "transition_statistics": transition_stats,
                "completion_rate": completion_rate,
                "average_processing_time": avg_processing_time,
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"获取状态统计信息失败: {e}")
            return {"error": str(e)}
    
    async def get_performance_metrics(self, db: AsyncSession, hours: int = 24) -> Dict[str, Any]:
        """获取性能指标"""
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=hours)
            
            # 查询任务处理量
            task_volume = await self._get_task_volume(db, start_time, end_time)
            
            # 查询错误率
            error_rate = await self._get_error_rate(db, start_time, end_time)
            
            # 查询超时率
            timeout_rate = await self._get_timeout_rate(db, start_time, end_time)
            
            # 查询重试率
            retry_rate = await self._get_retry_rate(db, start_time, end_time)
            
            return {
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "hours": hours
                },
                "task_volume": task_volume,
                "error_rate": error_rate,
                "timeout_rate": timeout_rate,
                "retry_rate": retry_rate,
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"获取性能指标失败: {e}")
            return {"error": str(e)}
    
    async def get_audit_logs(
        self, 
        db: AsyncSession, 
        job_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取审计日志"""
        try:
            query = select(JobStateAuditLog)
            
            # 添加过滤条件
            if job_id:
                query = query.where(JobStateAuditLog.job_id == job_id)
            
            if start_time:
                query = query.where(JobStateAuditLog.created_at >= start_time)
            
            if end_time:
                query = query.where(JobStateAuditLog.created_at <= end_time)
            
            # 按时间倒序排列
            query = query.order_by(JobStateAuditLog.created_at.desc())
            
            # 限制数量
            query = query.limit(limit)
            
            result = await db.execute(query)
            logs = result.scalars().all()
            
            # 转换为字典格式
            log_list = []
            for log in logs:
                log_dict = {
                    "id": log.id,
                    "job_id": log.job_id,
                    "from_state": log.from_state,
                    "to_state": log.to_state,
                    "transition_reason": log.transition_reason,
                    "operator_id": log.operator_id,
                    "operator_type": log.operator_type,
                    "transition_metadata": log.transition_metadata,
                    "created_at": log.created_at.isoformat()
                }
                log_list.append(log_dict)
            
            return log_list
            
        except Exception as e:
            logger.error(f"获取审计日志失败: {e}")
            return []
    
    async def get_system_health(self, db: AsyncSession) -> Dict[str, Any]:
        """获取系统健康状态"""
        try:
            # 检查Redis连接
            redis_status = await self._check_redis_health()
            
            # 检查数据库连接
            db_status = await self._check_database_health(db)
            
            # 检查超时任务
            timeout_status = await self._check_timeout_health()
            
            # 计算整体健康状态
            overall_health = "healthy"
            if not redis_status["healthy"] or not db_status["healthy"]:
                overall_health = "unhealthy"
            elif timeout_status["timeout_tasks"] > 0:
                overall_health = "degraded"
            
            return {
                "overall_health": overall_health,
                "redis_status": redis_status,
                "database_status": db_status,
                "timeout_status": timeout_status,
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"获取系统健康状态失败: {e}")
            return {
                "overall_health": "unhealthy",
                "error": str(e),
                "timestamp": time.time()
            }
    
    # 私有方法
    
    async def _get_state_distribution(self, db: AsyncSession, start_time: datetime, end_time: datetime) -> Dict[str, int]:
        """获取状态分布"""
        try:
            result = await db.execute(
                select(Job.status, func.count(Job.job_id))
                .where(and_(Job.created_at >= start_time, Job.created_at <= end_time))
                .group_by(Job.status)
            )
            
            distribution = {}
            for status, count in result:
                distribution[status] = count
            
            return distribution
            
        except Exception as e:
            logger.error(f"获取状态分布失败: {e}")
            return {}
    
    async def _get_transition_statistics(self, db: AsyncSession, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        """获取状态转换统计"""
        try:
            # 查询转换次数
            result = await db.execute(
                select(
                    JobStateAuditLog.from_state,
                    JobStateAuditLog.to_state,
                    func.count(JobStateAuditLog.id).label('count')
                )
                .where(and_(JobStateAuditLog.created_at >= start_time, JobStateAuditLog.created_at <= end_time))
                .group_by(JobStateAuditLog.from_state, JobStateAuditLog.to_state)
                .order_by(func.count(JobStateAuditLog.id).desc())
            )
            
            transitions = []
            for from_state, to_state, count in result:
                transitions.append({
                    "from_state": from_state,
                    "to_state": to_state,
                    "count": count
                })
            
            return {
                "transitions": transitions,
                "total_transitions": sum(t["count"] for t in transitions)
            }
            
        except Exception as e:
            logger.error(f"获取状态转换统计失败: {e}")
            return {"transitions": [], "total_transitions": 0}
    
    async def _get_completion_rate(self, db: AsyncSession, start_time: datetime, end_time: datetime) -> float:
        """获取任务完成率"""
        try:
            # 查询总任务数
            total_result = await db.execute(
                select(func.count(Job.job_id))
                .where(and_(Job.created_at >= start_time, Job.created_at <= end_time))
            )
            total_tasks = total_result.scalar()
            
            if total_tasks == 0:
                return 0.0
            
            # 查询完成的任务数
            completed_result = await db.execute(
                select(func.count(Job.job_id))
                .where(and_(
                    Job.created_at >= start_time, 
                    Job.created_at <= end_time,
                    Job.status == "completed"
                ))
            )
            completed_tasks = completed_result.scalar()
            
            return round(completed_tasks / total_tasks * 100, 2)
            
        except Exception as e:
            logger.error(f"获取任务完成率失败: {e}")
            return 0.0
    
    async def _get_average_processing_time(self, db: AsyncSession, start_time: datetime, end_time: datetime) -> float:
        """获取平均处理时间（秒）"""
        try:
            result = await db.execute(
                select(
                    func.avg(
                        func.extract('epoch', Job.updated_at - Job.created_at)
                    )
                )
                .where(and_(
                    Job.created_at >= start_time,
                    Job.created_at <= end_time,
                    Job.status.in_(["completed", "failed"])
                ))
            )
            
            avg_time = result.scalar()
            return round(avg_time or 0, 2)
            
        except Exception as e:
            logger.error(f"获取平均处理时间失败: {e}")
            return 0.0
    
    async def _get_task_volume(self, db: AsyncSession, start_time: datetime, end_time: datetime) -> Dict[str, int]:
        """获取任务处理量"""
        try:
            # 按小时统计任务量
            result = await db.execute(
                select(
                    func.date_trunc('hour', Job.created_at).label('hour'),
                    func.count(Job.job_id).label('count')
                )
                .where(and_(Job.created_at >= start_time, Job.created_at <= end_time))
                .group_by(func.date_trunc('hour', Job.created_at))
                .order_by(func.date_trunc('hour', Job.created_at))
            )
            
            hourly_volume = {}
            for hour, count in result:
                hourly_volume[hour.isoformat()] = count
            
            return {
                "hourly_volume": hourly_volume,
                "total_tasks": sum(hourly_volume.values())
            }
            
        except Exception as e:
            logger.error(f"获取任务处理量失败: {e}")
            return {"hourly_volume": {}, "total_tasks": 0}
    
    async def _get_error_rate(self, db: AsyncSession, start_time: datetime, end_time: datetime) -> float:
        """获取错误率"""
        try:
            # 查询总任务数
            total_result = await db.execute(
                select(func.count(Job.job_id))
                .where(and_(Job.created_at >= start_time, Job.created_at <= end_time))
            )
            total_tasks = total_result.scalar()
            
            if total_tasks == 0:
                return 0.0
            
            # 查询失败的任务数
            failed_result = await db.execute(
                select(func.count(Job.job_id))
                .where(and_(
                    Job.created_at >= start_time,
                    Job.created_at <= end_time,
                    Job.status == "failed"
                ))
            )
            failed_tasks = failed_result.scalar()
            
            return round(failed_tasks / total_tasks * 100, 2)
            
        except Exception as e:
            logger.error(f"获取错误率失败: {e}")
            return 0.0
    
    async def _get_timeout_rate(self, db: AsyncSession, start_time: datetime, end_time: datetime) -> float:
        """获取超时率"""
        try:
            # 查询总任务数
            total_result = await db.execute(
                select(func.count(Job.job_id))
                .where(and_(Job.created_at >= start_time, Job.created_at <= end_time))
            )
            total_tasks = total_result.scalar()
            
            if total_tasks == 0:
                return 0.0
            
            # 查询超时失败的任务数（通过错误信息判断）
            timeout_result = await db.execute(
                select(func.count(Job.job_id))
                .where(and_(
                    Job.created_at >= start_time,
                    Job.created_at <= end_time,
                    Job.status == "failed",
                    Job.error_message.like("%超时%")
                ))
            )
            timeout_tasks = timeout_result.scalar()
            
            return round(timeout_tasks / total_tasks * 100, 2)
            
        except Exception as e:
            logger.error(f"获取超时率失败: {e}")
            return 0.0
    
    async def _get_retry_rate(self, db: AsyncSession, start_time: datetime, end_time: datetime) -> float:
        """获取重试率"""
        try:
            # 查询总任务数
            total_result = await db.execute(
                select(func.count(Job.job_id))
                .where(and_(Job.created_at >= start_time, Job.created_at <= end_time))
            )
            total_tasks = total_result.scalar()
            
            if total_tasks == 0:
                return 0.0
            
            # 查询有重试记录的任务数
            retry_result = await db.execute(
                select(func.count(func.distinct(JobStateAuditLog.job_id)))
                .where(and_(
                    JobStateAuditLog.created_at >= start_time,
                    JobStateAuditLog.created_at <= end_time,
                    JobStateAuditLog.transition_reason.like("%retry%")
                ))
            )
            retry_tasks = retry_result.scalar()
            
            return round(retry_tasks / total_tasks * 100, 2)
            
        except Exception as e:
            logger.error(f"获取重试率失败: {e}")
            return 0.0
    
    async def _check_redis_health(self) -> Dict[str, Any]:
        """检查Redis健康状态"""
        try:
            await self.redis.ping()
            return {"healthy": True, "status": "connected"}
        except Exception as e:
            return {"healthy": False, "status": "disconnected", "error": str(e)}
    
    async def _check_database_health(self, db: AsyncSession) -> Dict[str, Any]:
        """检查数据库健康状态"""
        try:
            await db.execute(select(1))
            return {"healthy": True, "status": "connected"}
        except Exception as e:
            return {"healthy": False, "status": "disconnected", "error": str(e)}
    
    
    async def _check_timeout_health(self) -> Dict[str, Any]:
        """检查超时健康状态"""
        try:
            # 查询超时任务
            pattern = "job_timeout:*"
            keys = await self.redis.keys(pattern)
            
            timeout_tasks = 0
            for key in keys:
                ttl = await self.redis.ttl(key)
                if ttl <= 0:
                    timeout_tasks += 1
            
            return {
                "total_timeout_tasks": len(keys),
                "timeout_tasks": timeout_tasks,
                "healthy": timeout_tasks == 0
            }
            
        except Exception as e:
            return {"healthy": False, "error": str(e)}
