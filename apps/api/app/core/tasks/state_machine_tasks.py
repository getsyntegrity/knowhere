"""
状态机相关定时任务
"""
import asyncio
from typing import Any, Dict

from app.core.celery_app import get_celery_app
from app.core.database import get_db_context
from app.services.state_machine import JobStateMachine
from celery import Task
from loguru import logger

# 获取Celery应用
celery_app = get_celery_app()


class StateMachineBaseTask(Task):
    """状态机基础任务类"""
    
    def on_success(self, retval, task_id, args, kwargs):
        """任务成功回调"""
        logger.info(f"状态机任务 {task_id} 执行成功")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败回调"""
        logger.error(f"状态机任务 {task_id} 执行失败: {exc}")


@celery_app.task(bind=True, base=StateMachineBaseTask, name='app.tasks.state_machine_tasks.check_timeout_tasks')
def check_timeout_tasks(self):
    """
    检查超时任务 - 已废弃
    
    注意：此任务已废弃，因为使用Redis Keyspace Notifications时，
    超时会自动通过回调处理，无需定时检查。
    
    保留此任务仅用于：
    1. 监控和统计
    2. 健康检查
    """
    try:
        # 异步执行超时检查
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(_check_timeout_tasks_async())
            return result
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"检查超时任务失败: {e}")
        raise


async def _check_timeout_tasks_async() -> Dict[str, Any]:
    """异步检查超时任务 - 已废弃"""
    try:
        # 获取数据库会话
        async with get_db_context() as db:
            # 初始化状态机
            state_machine = JobStateMachine()
            
            # 检查超时任务（Keyspace Notifications模式下通常返回空列表）
            timeout_tasks = await state_machine.check_timeout_tasks(db)
            
            # 检查超时监听器状态
            is_listener_running = await state_machine.is_timeout_listener_running()
            
            logger.info(f"超时检查完成: 发现 {len(timeout_tasks)} 个超时任务, 监听器运行状态: {is_listener_running}")
            return {
                "status": "success",
                "timeout_tasks_count": len(timeout_tasks),
                "listener_running": is_listener_running,
                "message": "使用Redis Keyspace Notifications，超时会自动处理",
                "note": "此任务已废弃，仅用于监控"
            }
                
    except Exception as e:
        logger.error(f"异步检查超时任务失败: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@celery_app.task(bind=True, base=StateMachineBaseTask, name='app.tasks.state_machine_tasks.sync_all_states')
def sync_all_states(self):
    """同步所有状态"""
    try:
        # 异步执行状态同步
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(_sync_all_states_async())
            return result
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"同步所有状态失败: {e}")
        raise


async def _sync_all_states_async() -> Dict[str, Any]:
    """异步同步所有状态"""
    try:
        # 获取数据库会话
        async with get_db_context() as db:
            # 初始化状态机
            state_machine = JobStateMachine()
            
            # 批量同步所有状态
            sync_result = await state_machine.batch_sync_all_states(db)
            
            logger.info(f"状态同步完成: {sync_result}")
            return {
                "status": "success",
                "sync_result": sync_result
            }
            
    except Exception as e:
        logger.error(f"异步同步所有状态失败: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@celery_app.task(bind=True, base=StateMachineBaseTask, name='app.tasks.state_machine_tasks.state_machine_maintenance')
def state_machine_maintenance(self):
    """状态机维护任务"""
    try:
        # 异步执行维护
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(_state_machine_maintenance_async())
            return result
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"状态机维护失败: {e}")
        raise


async def _state_machine_maintenance_async() -> Dict[str, Any]:
    """异步状态机维护"""
    try:
        # 获取数据库会话
        async with get_db_context() as db:
            # 初始化状态机
            state_machine = JobStateMachine()
            
            # 执行维护操作
            maintenance_result = await state_machine.maintenance(db)
            
            logger.info(f"状态机维护完成: {maintenance_result}")
            return {
                "status": "success",
                "maintenance_result": maintenance_result
            }
            
    except Exception as e:
        logger.error(f"异步状态机维护失败: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@celery_app.task(bind=True, base=StateMachineBaseTask, name='app.tasks.state_machine_tasks.health_check')
def health_check(self):
    """健康检查任务"""
    try:
        # 异步执行健康检查
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(_health_check_async())
            return result
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        raise


async def _health_check_async() -> Dict[str, Any]:
    """异步健康检查"""
    try:
        # 获取数据库会话
        async with get_db_context() as db:
            # 初始化状态机
            state_machine = JobStateMachine()
            
            # 执行健康检查
            health_result = await state_machine.health_check(db)
            
            logger.info(f"健康检查完成: {health_result}")
            return health_result
            
    except Exception as e:
        logger.error(f"异步健康检查失败: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

