"""
异步消息消费者服务
使用aio-pika监听RabbitMQ队列并处理消息
"""
import asyncio
import json
from typing import Any, Dict, Optional

import aio_pika
from aio_pika import IncomingMessage
from loguru import logger

from app.services.messaging.async_config import (
    get_exchange_config,
    get_queue_config,
    get_queue_name,
    get_routing_key,
)
from app.services.messaging.async_connection import get_connection_manager
from app.services.messaging.message_handlers import (
    handle_job_failure,
    handle_job_progress_update,
    handle_job_result,
    handle_job_status_update,
)


class MessageConsumer:
    """异步消息消费者 - 使用aio-pika监听RabbitMQ队列"""
    
    # 重试配置
    MAX_RETRIES = {
        'job_status_update': 3,
        'job_progress_update': 0,  # 不重试
        'job_result': 2,
        'job_failure': 3,
    }
    
    RETRY_DELAYS = {
        'job_status_update': 60,  # 秒
        'job_result': 120,
        'job_failure': 60,
    }
    
    # 超时配置（秒）
    TIMEOUTS = {
        'job_status_update': 30 * 60,  # 30分钟
        'job_progress_update': 5 * 60,  # 5分钟
        'job_result': 30 * 60,  # 30分钟
        'job_failure': 10 * 60,  # 10分钟
    }
    
    def __init__(self):
        """初始化消息消费者"""
        self._connection_manager = get_connection_manager()
        self._consumers = []  # 存储消费者任务
        self._running = False
        self._stop_event = asyncio.Event()
    
    async def start_consuming(self):
        """异步启动消费"""
        if self._running:
            logger.warning("消息消费者已在运行")
            return
        
        self._running = True
        self._stop_event.clear()
        logger.info("启动异步消息消费者...")
        
        try:
            # 建立连接和通道
            await self._connection_manager.connect()
            channel = await self._connection_manager.get_channel()
            
            # 声明交换器
            exchange_config = get_exchange_config()
            exchange = await channel.declare_exchange(
                exchange_config["name"],
                exchange_config["type"],
                durable=exchange_config["durable"],
                auto_delete=exchange_config["auto_delete"],
            )
            
            # 创建并启动消费者
            message_handlers = {
                'job_status_update': handle_job_status_update,
                'job_progress_update': handle_job_progress_update,
                'job_result': handle_job_result,
                'job_failure': handle_job_failure,
            }
            
            for message_type, handler_func in message_handlers.items():
                queue_name = get_queue_name(message_type)
                routing_key = get_routing_key(message_type)
                
                # 声明队列
                queue_config = get_queue_config(queue_name)
                queue = await channel.declare_queue(
                    queue_name,
                    durable=queue_config["durable"],
                    auto_delete=queue_config["auto_delete"],
                    exclusive=queue_config["exclusive"],
                    arguments=queue_config["arguments"],
                )
                
                # 绑定队列到交换器
                await queue.bind(exchange, routing_key=routing_key)
                
                # 创建消费者任务
                consumer_task = asyncio.create_task(
                    self._consume_queue(queue, handler_func, message_type)
                )
                self._consumers.append(consumer_task)
                logger.info(f"已启动消费者: {message_type} -> {queue_name}")
            
            logger.info("所有消息消费者已启动，开始监听消息...")
            
            # 等待停止信号
            await self._stop_event.wait()
            
        except Exception as e:
            logger.error(f"消息消费者启动失败: {e}", exc_info=True)
            self._running = False
            raise
    
    async def stop_consuming(self):
        """优雅停止消费"""
        if not self._running:
            return
        
        logger.info("正在停止消息消费者...")
        self._running = False
        self._stop_event.set()
        
        # 等待所有消费者任务完成
        if self._consumers:
            logger.info(f"等待 {len(self._consumers)} 个消费者任务完成...")
            await asyncio.gather(*self._consumers, return_exceptions=True)
            self._consumers = []
        
        # 关闭连接
        await self._connection_manager.close()
        
        logger.info("消息消费者已停止")
    
    async def _consume_queue(
        self,
        queue: aio_pika.Queue,
        handler_func,
        message_type: str
    ):
        """消费队列消息"""
        try:
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    if not self._running:
                        break
                    
                    # 手动处理消息确认，不使用message.process()的自动确认
                    # 这样可以更好地控制重试逻辑
                    try:
                        await self._process_message(message, handler_func, message_type)
                        # 处理成功，确认消息
                        await message.ack()
                    except Exception as e:
                        logger.error(f"处理消息时出错: {e}", exc_info=True)
                        # 消息处理失败，根据消息类型决定是否重新入队
                        try:
                            if message_type == 'job_progress_update':
                                # 进度更新失败不重试，直接确认
                                await message.ack()
                            else:
                                # 其他消息失败时拒绝并重新入队
                                await message.nack(requeue=True)
                        except Exception as ack_error:
                            logger.error(f"确认/拒绝消息时出错: {ack_error}")
        except asyncio.CancelledError:
            logger.info(f"消费者任务 {message_type} 已取消")
        except Exception as e:
            logger.error(f"消费队列 {queue.name} 时出错: {e}", exc_info=True)
    
    async def _process_message(
        self,
        message: IncomingMessage,
        handler_func,
        message_type: str
    ):
        """处理单个消息"""
        # 解析消息体
        message_data = await self._parse_message_body(message.body)
        if not message_data:
            logger.warning(f"无法解析消息体: {message_type}")
            # 无法解析的消息抛出异常，让外层确认
            raise ValueError(f"无法解析消息体: {message_type}")
        
        job_id = message_data.get('job_id', 'unknown')
        logger.debug(f"收到消息: {message_type}, job_id={job_id}")
        
        # 处理消息（带重试）
        result = await self._process_with_retry(
            handler_func,
            message_data,
            message_type
        )
        
        if result:
            logger.debug(f"消息处理成功: {message_type}, job_id={job_id}")
        else:
            logger.warning(f"消息处理失败: {message_type}, job_id={job_id}")
            # 处理失败时抛出异常，让外层处理确认/拒绝
            raise Exception(f"消息处理失败: {message_type}, job_id={job_id}")
    
    async def _process_with_retry(
        self,
        handler_func,
        message_data: Dict[str, Any],
        message_type: str
    ) -> bool:
        """
        带重试的消息处理
        
        Args:
            handler_func: 消息处理函数
            message_data: 消息数据
            message_type: 消息类型
            
        Returns:
            是否处理成功
        """
        max_retries = self.MAX_RETRIES.get(message_type, 0)
        retry_delay = self.RETRY_DELAYS.get(message_type, 60)
        timeout = self.TIMEOUTS.get(message_type, 30 * 60)
        
        for attempt in range(max_retries + 1):
            try:
                # 使用超时控制
                result = await asyncio.wait_for(
                    handler_func(message_data),
                    timeout=timeout
                )
                return result.get('status') == 'success' if result else False
                
            except asyncio.TimeoutError:
                logger.error(
                    f"处理{message_type}超时: job_id={message_data.get('job_id')}, "
                    f"attempt={attempt + 1}/{max_retries + 1}, timeout={timeout}秒"
                )
                if attempt < max_retries:
                    wait_time = retry_delay * (2 ** attempt)
                    logger.info(f"等待{wait_time}秒后重试...")
                    await asyncio.sleep(wait_time)
                else:
                    return False
                    
            except Exception as e:
                logger.error(
                    f"处理{message_type}失败: job_id={message_data.get('job_id')}, "
                    f"attempt={attempt + 1}/{max_retries + 1}, error={e}"
                )
                if attempt < max_retries:
                    wait_time = retry_delay * (2 ** attempt)
                    logger.info(f"等待{wait_time}秒后重试...")
                    await asyncio.sleep(wait_time)
                else:
                    return False
        
        return False
    
    async def _parse_message_body(self, body: bytes) -> Optional[Dict[str, Any]]:
        """解析消息体"""
        try:
            if isinstance(body, bytes):
                body_str = body.decode('utf-8')
            else:
                body_str = str(body)
            
            return json.loads(body_str)
            
        except json.JSONDecodeError as e:
            logger.error(f"无法解析消息体为JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"解析消息体失败: {e}")
            return None


def get_message_consumer() -> MessageConsumer:
    """获取消息消费者实例"""
    return MessageConsumer()
