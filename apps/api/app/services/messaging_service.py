"""
API服务的消息消费者服务
在API服务启动时启动消息消费者
"""
import threading

from app.services.messaging import get_message_consumer
from loguru import logger


class MessagingService:
    """消息服务管理器"""
    
    def __init__(self):
        self.consumer = None
        self.consumer_thread = None
        self._running = False
    
    def start(self):
        """启动消息消费者（在后台线程中运行）"""
        if self._running:
            logger.warning("消息消费者已在运行")
            return
        
        try:
            self.consumer = get_message_consumer()
            self._running = True
            
            # 在后台线程中启动消息消费者
            self.consumer_thread = threading.Thread(
                target=self._run_consumer,
                daemon=True,
                name="MessageConsumer"
            )
            self.consumer_thread.start()
            logger.info("消息消费者已在后台线程中启动")
            
        except Exception as e:
            logger.error(f"启动消息消费者失败: {e}")
            self._running = False
            raise
    
    def _run_consumer(self):
        """在后台线程中运行消息消费者"""
        try:
            logger.info("消息消费者线程启动")
            self.consumer.start_consuming()
        except Exception as e:
            logger.error(f"消息消费者线程出错: {e}")
            self._running = False
    
    def stop(self):
        """停止消息消费者"""
        if not self._running:
            return
        
        logger.info("正在停止消息消费者...")
        self._running = False
        
        if self.consumer:
            try:
                self.consumer.stop_consuming()
            except Exception as e:
                logger.error(f"停止消息消费者时出错: {e}")
        
        if self.consumer_thread and self.consumer_thread.is_alive():
            self.consumer_thread.join(timeout=5)
        
        logger.info("消息消费者已停止")


# 创建全局消息服务实例
messaging_service = MessagingService()

