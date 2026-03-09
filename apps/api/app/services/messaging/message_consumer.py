"""
异步消息消费者服务
使用aio-pika监听RabbitMQ队列并处理消息
"""
import asyncio
import json
from typing import Any, Dict, Optional
from shared.core.exceptions.domain_exceptions import KnowhereException

from aio_pika import IncomingMessage
from aio_pika.exceptions import (
    AMQPChannelError,
    AMQPConnectionError,
    ChannelClosed,
    ChannelInvalidStateError,
)
from loguru import logger

from shared.services.messaging.async_config import (
    get_exchange_config,
    get_queue_config,
    get_queue_name,
    get_routing_key,
)
from shared.services.messaging.async_connection import get_connection_manager
from shared.core.logging import LogEvent
from app.services.messaging.message_handlers import (
    handle_job_failure,
    handle_job_progress_update,
    handle_job_result,
    handle_job_status_update,
)
from shared.core.exceptions.domain_exceptions import WorkerHandlingException


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
            logger.warning("Message consumer is already running")
            return

        self._running = True
        self._stop_event.clear()
        logger.info("Starting async message consumer...")

        try:
            # Establish initial connection
            await self._connection_manager.connect()

            # 创建并启动消费者
            message_handlers = {
                'job_status_update': handle_job_status_update,
                'job_progress_update': handle_job_progress_update,
                'job_result': handle_job_result,
                'job_failure': handle_job_failure,
            }

            for message_type, handler_func in message_handlers.items():
                # 创建消费者任务 — each task manages its own channel/queue
                consumer_task = asyncio.create_task(
                    self._consume_queue(handler_func, message_type)
                )
                self._consumers.append(consumer_task)
                logger.debug(f"Started consumer: {message_type}")

            logger.info("All message consumers started and listening")

            # 等待停止信号
            await self._stop_event.wait()

        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"Failed to start message consumer: {e}", exc_info=True)
            self._running = False
            raise WorkerHandlingException(
                internal_message=f"Failed to start message consumer: {str(e)}",
                original_exception=e
            )
    
    async def stop_consuming(self, timeout: float = 10.0):
        """
        优雅停止消费
        
        Args:
            timeout: 等待消费者任务完成的最大超时时间（秒）
        """
        if not self._running:
            return
        
        logger.info("Stopping message consumer...")
        self._running = False
        self._stop_event.set()
        
        # 取消所有消费者任务
        if self._consumers:
            logger.debug(f"Cancelling {len(self._consumers)} consumer tasks")
            for consumer_task in self._consumers:
                if not consumer_task.done():
                    consumer_task.cancel()
            
            # 等待所有消费者任务完成，设置超时
            logger.debug(f"Waiting for consumer tasks to finish (timeout: {timeout}s)")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._consumers, return_exceptions=True),
                    timeout=timeout
                )
                logger.debug("All consumer tasks completed")
            except asyncio.TimeoutError:
                logger.warning(f"Timed out waiting for consumer tasks ({timeout}s), forcing close")
                # 超时后，强制取消所有未完成的任务
                for consumer_task in self._consumers:
                    if not consumer_task.done():
                        try:
                            consumer_task.cancel()
                        except Exception as e:
                            logger.warning(f"Error while cancelling consumer task: {e}")
            
            self._consumers = []
        
        # 关闭连接
        try:
            await self._connection_manager.close()
            logger.info("RabbitMQ connection closed")
        except Exception as e:
            logger.warning(f"Error while closing RabbitMQ connection: {e}")
        
        logger.info("Message consumer stopped")
    
    RECONNECT_DELAY = 5  # seconds between reconnection attempts

    async def _consume_queue(
        self,
        handler_func,
        message_type: str
    ):
        """
        消费队列消息 with automatic reconnection.

        Outer loop: reconnects channel and re-declares queue on AMQP errors.
        Inner loop: processes messages, breaks on AMQP errors to trigger reconnect.
        """
        queue_name = get_queue_name(message_type)
        routing_key = get_routing_key(message_type)
        exchange_config = get_exchange_config()

        while self._running:
            try:
                await self._consume_queue_inner(
                    handler_func, message_type, queue_name, routing_key, exchange_config
                )
                # Normal exit (stop_event set) — don't reconnect
                break
            except asyncio.CancelledError:
                raise
            except (AMQPConnectionError, AMQPChannelError, ChannelClosed, ChannelInvalidStateError) as e:
                if not self._running:
                    break
                logger.bind(event=LogEvent.NETWORK_AMQP_CONSUME_ERROR.value).warning(
                    f"Consumer reconnecting: queue={queue_name}, "
                    f"error_type={type(e).__name__}, error={e}, "
                    f"retry_in={self.RECONNECT_DELAY}s"
                )
                await asyncio.sleep(self.RECONNECT_DELAY)
            except Exception as e:
                if not self._running:
                    break
                logger.error(
                    f"Unexpected error in consumer, reconnecting: queue={queue_name}, error={e}",
                    exc_info=True
                )
                await asyncio.sleep(self.RECONNECT_DELAY)

        logger.debug(f"Consumer exited: {message_type}")

    async def _consume_queue_inner(
        self,
        handler_func,
        message_type: str,
        queue_name: str,
        routing_key: str,
        exchange_config: dict,
    ):
        """Inner consume loop. Raises AMQP exceptions to trigger reconnection."""
        # Get a fresh channel via connect_robust (handles connection recovery)
        channel = await self._connection_manager.get_channel()
        exchange = await channel.declare_exchange(
            exchange_config["name"],
            exchange_config["type"],
            durable=exchange_config["durable"],
            auto_delete=exchange_config["auto_delete"],
        )
        queue_config = get_queue_config(queue_name)
        queue = await channel.declare_queue(
            queue_name,
            durable=queue_config["durable"],
            auto_delete=queue_config["auto_delete"],
            exclusive=queue_config["exclusive"],
            arguments=queue_config["arguments"],
        )
        await queue.bind(exchange, routing_key=routing_key)

        logger.info(f"Consumer connected: queue={queue_name}, type={message_type}")

        message_task: asyncio.Task | None = None
        stop_task: asyncio.Task | None = None
        try:
            async with queue.iterator() as queue_iter:
                stop_task = asyncio.create_task(self._stop_event.wait())

                while self._running:
                    try:
                        # 如果消息任务已完成或不存在，创建新的消息接收任务
                        if message_task is None or message_task.done():
                            if message_task and message_task.done():
                                # 如果任务已完成，检查是否有异常
                                try:
                                    message_task.result()
                                except StopAsyncIteration:
                                    logger.debug(f"Queue iterator ended: {message_type}")
                                    break
                                except Exception as e:
                                    logger.error(f"Message receive task failed: {e}")
                                    break
                            
                            # 创建新的消息接收任务
                            message_task = asyncio.create_task(queue_iter.__anext__())
                        
                        # 同时等待消息和停止事件
                        # 使用 asyncio.wait 可以同时等待多个协程，哪个先完成就处理哪个
                        done, _ = await asyncio.wait(
                            [
                                message_task,
                                stop_task,
                            ],
                            return_when=asyncio.FIRST_COMPLETED
                        )

                        # 检查是否收到停止信号
                        if self._stop_event.is_set() or not self._running:
                            logger.debug(f"Consumer stopping, exiting message loop: {message_type}")
                            # 如果消息任务已完成，需要处理消息
                            if message_task.done():
                                try:
                                    message = message_task.result()
                                    # 拒绝并重新入队
                                    try:
                                        await message.nack(requeue=True)
                                        logger.debug(f"Message requeued on shutdown: {message_type}")
                                    except Exception as e:
                                        logger.warning(f"Error while requeueing message: {e}")
                                except (StopAsyncIteration, asyncio.CancelledError):
                                    pass
                                except Exception as e:
                                    logger.warning(f"Error while reading pending message: {e}")
                            else:
                                message_task.cancel()
                                try:
                                    await message_task
                                except asyncio.CancelledError:
                                    pass
                            break
                        
                        # 处理收到的消息
                        if message_task in done:
                            try:
                                message = message_task.result()
                                message_task = None  # 重置任务，下次循环创建新任务
                                
                                logger.debug(f"Received message: {message_type}, queue={queue.name}")
                                # 手动处理消息确认，不使用message.process()的自动确认
                                # 这样可以更好地控制重试逻辑
                                try:
                                    await self._process_message(message, handler_func, message_type)
                                    # 处理成功，确认消息
                                    await message.ack()
                                    logger.debug(f"Message acked: {message_type}, queue={queue.name}")
                                except Exception as e:
                                    logger.error(f"Error while processing message: {message_type}, queue={queue.name}, error={e}", exc_info=True)
                                    # 消息处理失败，根据消息类型决定是否重新入队
                                    try:
                                        if message_type == 'job_progress_update':
                                            # 进度更新失败不重试，直接确认
                                            await message.ack()
                                            logger.warning(f"Progress update failed and was acked: {message_type}")
                                        else:
                                            # 其他消息失败时拒绝并重新入队
                                            await message.nack(requeue=True)
                                            logger.warning(f"Message processing failed and was requeued: {message_type}")
                                    except (AMQPConnectionError, AMQPChannelError, ChannelClosed, ChannelInvalidStateError) as ack_error:
                                        logger.bind(event=LogEvent.NETWORK_AMQP_CONSUME_ERROR.value).error(
                                            f"AMQP error during ack/nack: queue={queue_name}, "
                                            f"error_type={type(ack_error).__name__}, error={ack_error}"
                                        )
                                        raise  # Propagate to outer reconnection loop
                                    except Exception as ack_error:
                                        logger.error(f"Error while acking/nacking message: {message_type}, error={ack_error}", exc_info=True)
                            except StopAsyncIteration:
                                logger.debug(f"Queue iterator ended: {message_type}")
                                break
                            except asyncio.CancelledError:
                                raise
                            except (AMQPConnectionError, AMQPChannelError, ChannelClosed, ChannelInvalidStateError) as e:
                                logger.bind(event=LogEvent.NETWORK_AMQP_CONSUME_ERROR.value).error(
                                    f"AMQP error while receiving message: queue={queue_name}, "
                                    f"error_type={type(e).__name__}, error={e}"
                                )
                                raise  # Propagate to outer reconnection loop
                            except Exception as e:
                                logger.error(f"Error while receiving message: {message_type}, error={e}", exc_info=True)
                                message_task = None  # 重置任务，继续循环
                    
                    except asyncio.CancelledError:
                        # 任务被取消，重新抛出异常以便上层处理
                        logger.debug(f"Consumer task cancelled: {message_type}")
                        raise
                
                logger.debug(f"Consumer loop exited: {message_type}")

        except asyncio.CancelledError:
            logger.debug(f"Consumer task {message_type} cancelled")
            raise
        except (AMQPConnectionError, AMQPChannelError, ChannelClosed, ChannelInvalidStateError):
            raise  # Let outer _consume_queue handle reconnection
        finally:
            if message_task and not message_task.done():
                message_task.cancel()
                try:
                    await message_task
                except asyncio.CancelledError:
                    pass

            if stop_task and not stop_task.done():
                stop_task.cancel()
                try:
                    await stop_task
                except asyncio.CancelledError:
                    pass
    
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
            logger.warning(f"Failed to parse message body: {message_type}")
            raise WorkerHandlingException(
                internal_message=f"Failed to parse message body: {message_type}"
            )
        
        job_id = message_data.get('job_id', 'unknown')
        logger.debug(f"Received message: {message_type}, job_id={job_id}")
        
        # 处理消息（带重试）
        result = await self._process_with_retry(
            handler_func,
            message_data,
            message_type
        )
        
        if result:
            logger.debug(f"Message processed successfully: {message_type}, job_id={job_id}")
        else:
            logger.warning(f"Message processing failed: {message_type}, job_id={job_id}")
            raise WorkerHandlingException(
                internal_message=f"Message processing failed: {message_type}, job_id={job_id}"
            )
    
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
                    f"Timeout while processing {message_type}: job_id={message_data.get('job_id')}, "
                    f"attempt={attempt + 1}/{max_retries + 1}, timeout={timeout}s"
                )
                if attempt < max_retries:
                    wait_time = retry_delay * (2 ** attempt)
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Processing {message_type} timed out, max retries reached")
                    return False
                    
            except Exception as e:
                logger.error(
                    f"Failed to process {message_type}: job_id={message_data.get('job_id')}, "
                    f"attempt={attempt + 1}/{max_retries + 1}, error={e}",
                    exc_info=True
                )
                if attempt < max_retries:
                    wait_time = retry_delay * (2 ** attempt)
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Processing {message_type} failed, max retries reached")
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
            logger.error(f"Failed to parse message body as JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to parse message body: {e}")
            return None


def get_message_consumer() -> MessageConsumer:
    """获取消息消费者实例"""
    return MessageConsumer()
