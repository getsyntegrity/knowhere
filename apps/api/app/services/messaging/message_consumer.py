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

from shared.services.messaging.async_config import (
    get_exchange_config,
    get_queue_config,
    get_queue_name,
    get_routing_key,
)
from shared.services.messaging.async_connection import get_connection_manager
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
    
    async def stop_consuming(self, timeout: float = 10.0):
        """
        优雅停止消费
        
        Args:
            timeout: 等待消费者任务完成的最大超时时间（秒）
        """
        if not self._running:
            return
        
        logger.info("正在停止消息消费者...")
        self._running = False
        self._stop_event.set()
        
        # 取消所有消费者任务
        if self._consumers:
            logger.info(f"取消 {len(self._consumers)} 个消费者任务...")
            for consumer_task in self._consumers:
                if not consumer_task.done():
                    consumer_task.cancel()
            
            # 等待所有消费者任务完成，设置超时
            logger.info(f"等待消费者任务完成（超时: {timeout}秒）...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._consumers, return_exceptions=True),
                    timeout=timeout
                )
                logger.info("所有消费者任务已正常完成")
            except asyncio.TimeoutError:
                logger.warning(f"等待消费者任务超时（{timeout}秒），强制关闭")
                # 超时后，强制取消所有未完成的任务
                for consumer_task in self._consumers:
                    if not consumer_task.done():
                        try:
                            consumer_task.cancel()
                        except Exception as e:
                            logger.warning(f"取消消费者任务时出错: {e}")
            
            self._consumers = []
        
        # 关闭连接
        try:
            await self._connection_manager.close()
            logger.info("RabbitMQ连接已关闭")
        except Exception as e:
            logger.warning(f"关闭RabbitMQ连接时出错: {e}")
        
        logger.info("消息消费者已停止")
    
    async def _consume_queue(
        self,
        queue: aio_pika.Queue,
        handler_func,
        message_type: str
    ):
        """
        消费队列消息
        
        使用 asyncio.wait 同时等待消息和停止事件，确保：
        1. 有消息时立即处理，不影响业务性能
        2. 停止时立即响应，不会阻塞
        """
        logger.info(f"开始消费队列: {queue.name}, 消息类型: {message_type}")
        try:
            async with queue.iterator() as queue_iter:
                logger.info(f"队列迭代器已创建，等待消息: {queue.name}")
                
                # 创建消息接收任务
                message_task = None
                
                while self._running:
                    try:
                        # 如果消息任务已完成或不存在，创建新的消息接收任务
                        if message_task is None or message_task.done():
                            if message_task and message_task.done():
                                # 如果任务已完成，检查是否有异常
                                try:
                                    message_task.result()
                                except StopAsyncIteration:
                                    logger.info(f"队列迭代器已结束: {message_type}")
                                    break
                                except Exception as e:
                                    logger.error(f"消息接收任务异常: {e}")
                                    break
                            
                            # 创建新的消息接收任务
                            message_task = asyncio.create_task(queue_iter.__anext__())
                        
                        # 同时等待消息和停止事件
                        # 使用 asyncio.wait 可以同时等待多个协程，哪个先完成就处理哪个
                        done, pending = await asyncio.wait(
                            [
                                message_task,
                                asyncio.create_task(self._stop_event.wait())
                            ],
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        
                        # 取消未完成的任务
                        for task in pending:
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                        
                        # 检查是否收到停止信号
                        if self._stop_event.is_set() or not self._running:
                            logger.info(f"消费者已停止，退出消息循环: {message_type}")
                            # 如果消息任务已完成，需要处理消息
                            if message_task.done():
                                try:
                                    message = message_task.result()
                                    # 拒绝并重新入队
                                    try:
                                        await message.nack(requeue=True)
                                        logger.info(f"消息已重新入队: {message_type}")
                                    except Exception as e:
                                        logger.warning(f"重新入队消息时出错: {e}")
                                except (StopAsyncIteration, asyncio.CancelledError):
                                    pass
                                except Exception as e:
                                    logger.warning(f"获取消息结果时出错: {e}")
                            break
                        
                        # 处理收到的消息
                        if message_task in done:
                            try:
                                message = message_task.result()
                                message_task = None  # 重置任务，下次循环创建新任务
                                
                                logger.info(f"收到新消息，开始处理: {message_type}, queue={queue.name}")
                                # 手动处理消息确认，不使用message.process()的自动确认
                                # 这样可以更好地控制重试逻辑
                                try:
                                    await self._process_message(message, handler_func, message_type)
                                    # 处理成功，确认消息
                                    await message.ack()
                                    logger.info(f"消息已确认: {message_type}, queue={queue.name}")
                                except Exception as e:
                                    logger.error(f"处理消息时出错: {message_type}, queue={queue.name}, error={e}", exc_info=True)
                                    # 消息处理失败，根据消息类型决定是否重新入队
                                    try:
                                        if message_type == 'job_progress_update':
                                            # 进度更新失败不重试，直接确认
                                            await message.ack()
                                            logger.warning(f"进度更新消息处理失败，已确认: {message_type}")
                                        else:
                                            # 其他消息失败时拒绝并重新入队
                                            await message.nack(requeue=True)
                                            logger.warning(f"消息处理失败，已重新入队: {message_type}")
                                    except Exception as ack_error:
                                        logger.error(f"确认/拒绝消息时出错: {message_type}, error={ack_error}", exc_info=True)
                            except StopAsyncIteration:
                                logger.info(f"队列迭代器已结束: {message_type}")
                                break
                            except asyncio.CancelledError:
                                logger.info(f"消息接收任务被取消: {message_type}")
                                raise
                            except Exception as e:
                                logger.error(f"获取消息时出错: {message_type}, error={e}", exc_info=True)
                                message_task = None  # 重置任务，继续循环
                    
                    except asyncio.CancelledError:
                        # 任务被取消，重新抛出异常以便上层处理
                        logger.info(f"消费者任务被取消: {message_type}")
                        raise
                
                logger.info(f"消费者循环已退出: {message_type}")
                
        except asyncio.CancelledError:
            logger.info(f"消费者任务 {message_type} 已取消")
            raise
        except Exception as e:
            logger.error(f"消费队列 {queue.name} 时出错: {e}", exc_info=True)
            raise
    
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
        logger.info(f"收到消息: {message_type}, job_id={job_id}")
        
        # 处理消息（带重试）
        result = await self._process_with_retry(
            handler_func,
            message_data,
            message_type
        )
        
        if result:
            logger.info(f"消息处理成功: {message_type}, job_id={job_id}")
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
                    logger.error(f"处理{message_type}超时，已达到最大重试次数")
                    return False
                    
            except Exception as e:
                logger.error(
                    f"处理{message_type}失败: job_id={message_data.get('job_id')}, "
                    f"attempt={attempt + 1}/{max_retries + 1}, error={e}",
                    exc_info=True
                )
                if attempt < max_retries:
                    wait_time = retry_delay * (2 ** attempt)
                    logger.info(f"等待{wait_time}秒后重试...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"处理{message_type}失败，已达到最大重试次数")
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
