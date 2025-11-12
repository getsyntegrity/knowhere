"""
启动Redis Keyspace Notifications监听器
"""
import asyncio
import signal
import sys
from typing import Dict, Any
from loguru import logger

from app.services.state_machine.manager import JobStateMachine
from app.core.database import get_db_context


class TimeoutListener:
    """超时监听器"""
    
    def __init__(self):
        self.state_machine = JobStateMachine()
        self.running = False
    
    async def start(self):
        """启动监听器"""
        try:
            # 设置超时回调
            self.state_machine.state_timeout.notification_handler.set_timeout_callback(
                self._handle_timeout_callback
            )
            
            # 启动监听
            self.running = True
            logger.info("启动Redis Keyspace Notifications监听器...")
            
            # 使用状态机管理器的启动方法
            await self.state_machine.start_timeout_listener()
            
        except Exception as e:
            logger.error(f"启动监听器失败: {e}")
            raise
    
    async def stop(self):
        """停止监听器"""
        try:
            self.running = False
            await self.state_machine.stop_timeout_listener()
            logger.info("监听器已停止")
        except Exception as e:
            logger.error(f"停止监听器失败: {e}")
    
    async def _handle_timeout_callback(self, timeout_info: Dict[str, Any]):
        """处理超时回调"""
        try:
            job_id = timeout_info["job_id"]
            state = timeout_info["state"]
            
            logger.warning(f"任务 {job_id} 在状态 {state} 超时")
            
            # 获取数据库会话并处理超时
            async with get_db_context() as db:
                # 标记任务为失败
                await self.state_machine.mark_failed(
                    db, job_id, 
                    f"任务在 {state} 状态超时",
                    "timeout_listener",
                    {
                        "timeout_reason": "state_timeout",
                        "timeout_state": state,
                        "timeout_metadata": timeout_info.get("metadata", {})
                    }
                )
                
                logger.info(f"任务 {job_id} 超时处理完成")
                
        except Exception as e:
            logger.error(f"处理任务 {timeout_info.get('job_id', 'unknown')} 超时失败: {e}")


async def main():
    """主函数"""
    listener = TimeoutListener()
    
    # 设置信号处理
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}，正在停止监听器...")
        asyncio.create_task(listener.stop())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await listener.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止...")
    except Exception as e:
        logger.error(f"监听器运行失败: {e}")
    finally:
        await listener.stop()


if __name__ == "__main__":
    asyncio.run(main())
