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
            logger.warning("Message consumer is already running")
            return
        
        try:
            self.consumer = get_message_consumer()
            self._running = True
            
            # 在事件循环中启动消费者任务
            self.consumer_task = asyncio.create_task(self.consumer.start_consuming())
            logger.debug("Message consumer task scheduled on event loop")
            
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"Failed to start message consumer: {e}")
            self._running = False
            raise WorkerHandlingException(
                internal_message=f"Failed to start message consumer: {str(e)}",
                original_exception=e
            )
    
    async def stop(self):
        """停止消息消费者（异步）"""
        if not self._running:
            return
        
        logger.debug("Stopping message consumer service")
        self._running = False
        
        if self.consumer:
            try:
                await self.consumer.stop_consuming()
            except Exception as e:
                logger.error(f"Error while stopping message consumer: {e}")
        
        if self.consumer_task and not self.consumer_task.done():
            try:
                self.consumer_task.cancel()
                await self.consumer_task
            except asyncio.CancelledError:
                logger.debug("Message consumer task cancelled")
            except Exception as e:
                logger.error(f"Error while cancelling message consumer task: {e}")
        
        logger.debug("Message consumer service stopped")


# 创建全局消息服务实例
messaging_service = MessagingService()
