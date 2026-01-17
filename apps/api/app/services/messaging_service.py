"""
API服务的异步消息消费者服务
在FastAPI生命周期中启动和停止消息消费者
"""
import asyncio
from typing import Optional

from app.services.messaging.message_consumer import get_message_consumer
from shared.core.exceptions.domain_exceptions import KnowhereException, WorkerHandlingException
from loguru import logger


class MessagingService:
    """异步消息服务管理器"""
    
    def __init__(self):
        self.consumer = None
        self.consumer_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self):
        """启动消息消费者（异步）"""
        if self._running:
            logger.warning("消息消费者已在运行")
            return
        
        try:
            self.consumer = get_message_consumer()
            self._running = True
            
            # 在事件循环中启动消费者任务
            self.consumer_task = asyncio.create_task(self.consumer.start_consuming())
            logger.info("消息消费者已在事件循环中启动")
            
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"启动消息消费者失败: {e}")
            self._running = False
            raise WorkerHandlingException(
                internal_message=f"启动消息消费者失败: {str(e)}",
                original_exception=e
            )
    
    async def stop(self):
        """停止消息消费者（异步）"""
        if not self._running:
            return
        
        logger.info("正在停止消息消费者...")
        self._running = False
        
        if self.consumer:
            try:
                await self.consumer.stop_consuming()
            except Exception as e:
                logger.error(f"停止消息消费者时出错: {e}")
        
        if self.consumer_task and not self.consumer_task.done():
            try:
                self.consumer_task.cancel()
                await self.consumer_task
            except asyncio.CancelledError:
                logger.debug("消费者任务已取消")
            except Exception as e:
                logger.error(f"取消消费者任务时出错: {e}")
        
        logger.info("消息消费者已停止")


# 创建全局消息服务实例
messaging_service = MessagingService()
