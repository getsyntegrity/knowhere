"""
消息消费者服务
监听RabbitMQ队列并直接处理消息
"""
import asyncio
import json
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any

from kombu import Connection, Consumer, Exchange, Queue
from kombu.exceptions import TimeoutError as KombuTimeoutError, ChannelError
from loguru import logger

from app.core.config import app_config
from app.core.config.messaging import messaging_config
from app.services.messaging.message_handlers import (
    handle_job_status_update,
    handle_job_progress_update,
    handle_job_result,
    handle_job_failure,
)


class MessageConsumer:
    """消息消费者 - 监听RabbitMQ队列并直接处理消息"""
    
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
        self.broker_url = app_config.get_rabbitmq_url()
        self.exchange = Exchange(
            messaging_config.EXCHANGE_NAME,
            type=messaging_config.EXCHANGE_TYPE,
            durable=True
        )
        self._consumers = []
        self._running = False
        # 创建线程池用于执行异步处理函数
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="msg_handler")
    
    def _parse_message_body(self, body):
        """解析消息体（可能是字符串或字典）"""
        if isinstance(body, str):
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                logger.error(f"无法解析消息体为JSON: {body}")
                return None
        elif isinstance(body, dict):
            return body
        else:
            logger.error(f"未知的消息体类型: {type(body)}")
            return None
    
    def _run_async_with_retry(self, handler_func, message_data: Dict[str, Any], message_type: str):
        """
        运行异步处理函数，支持重试和超时
        
        Args:
            handler_func: 异步处理函数
            message_data: 消息数据
            message_type: 消息类型
            
        Returns:
            处理结果
        """
        max_retries = self.MAX_RETRIES.get(message_type, 0)
        retry_delay = self.RETRY_DELAYS.get(message_type, 60)
        timeout = self.TIMEOUTS.get(message_type, 30 * 60)
        
        last_exception = None
        
        for attempt in range(max_retries + 1):
            loop = None
            try:
                # 创建新的事件循环（因为在线程中运行）
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # 使用超时控制
                    result = loop.run_until_complete(
                        asyncio.wait_for(
                            handler_func(message_data),
                            timeout=timeout
                        )
                    )
                    return result
                finally:
                    # 确保所有待处理的任务完成后再关闭事件循环
                    try:
                        # 获取所有待处理的任务（排除当前任务）
                        try:
                            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                            if pending:
                                # 给任务一些时间完成
                                try:
                                    loop.run_until_complete(
                                        asyncio.wait_for(
                                            asyncio.gather(*pending, return_exceptions=True),
                                            timeout=2.0
                                        )
                                    )
                                except asyncio.TimeoutError:
                                    # 超时后取消所有未完成的任务
                                    for task in pending:
                                        if not task.done():
                                            task.cancel()
                                    # 等待取消完成
                                    loop.run_until_complete(
                                        asyncio.gather(*pending, return_exceptions=True)
                                    )
                        except RuntimeError:
                            # 如果事件循环已关闭，忽略错误
                            pass
                    except Exception as cleanup_error:
                        logger.warning(f"清理事件循环任务时出错: {cleanup_error}")
                    finally:
                        # 关闭事件循环
                        try:
                            if loop and not loop.is_closed():
                    loop.close()
                        except Exception as close_error:
                            logger.warning(f"关闭事件循环时出错: {close_error}")
                    
            except asyncio.TimeoutError:
                last_exception = TimeoutError(f"处理{message_type}超时（{timeout}秒）")
                logger.error(f"处理{message_type}超时: job_id={message_data.get('job_id')}, attempt={attempt + 1}/{max_retries + 1}")
                
            except Exception as e:
                last_exception = e
                logger.error(f"处理{message_type}失败: job_id={message_data.get('job_id')}, attempt={attempt + 1}/{max_retries + 1}, error={e}")
            
            # 如果不是最后一次尝试，等待后重试
            if attempt < max_retries:
                wait_time = retry_delay * (2 ** attempt)  # 指数退避
                logger.info(f"等待{wait_time}秒后重试: job_id={message_data.get('job_id')}")
                time.sleep(wait_time)
        
        # 所有重试都失败
        if last_exception:
            raise last_exception
        return {"status": "failed", "error": "处理失败"}
    
    def _process_message_async(self, handler_func, message_data: Dict[str, Any], message_type: str, message):
        """
        异步处理消息（在线程池中执行，不阻塞消息消费）
        
        Args:
            handler_func: 异步处理函数
            message_data: 消息数据
            message_type: 消息类型
            message: RabbitMQ消息对象
        """
        def _handle_result(future):
            """处理完成回调"""
            try:
                result = future.result()
                logger.debug(f"消息处理成功: {message_type}, job_id={message_data.get('job_id')}")
                message.ack()
            except Exception as e:
                logger.error(f"消息处理失败: {message_type}, job_id={message_data.get('job_id')}, error={e}")
                # 根据消息类型决定是否重新入队
                if message_type == 'job_progress_update':
                    # 进度更新失败不重试
                    message.ack()
                else:
                    message.reject(requeue=True)
        
        try:
            # 在线程池中执行处理，不阻塞消息消费
            # 使用add_done_callback确保非阻塞
            future = self._executor.submit(
                self._run_async_with_retry,
                handler_func,
                message_data,
                message_type
            )
            future.add_done_callback(_handle_result)
                    
        except Exception as e:
            logger.error(f"提交消息处理任务失败: {message_type}, job_id={message_data.get('job_id')}, error={e}")
            message.reject(requeue=True)
    
    def _on_status_update_message(self, body, message):
        """处理状态更新消息"""
        try:
            message_data = self._parse_message_body(body)
            if not message_data:
                message.reject(requeue=False)
                return
            
            logger.debug(f"收到状态更新消息: job_id={message_data.get('job_id')}")
            # 直接处理消息（异步执行，不阻塞）
            self._process_message_async(
                handle_job_status_update,
                message_data,
                'job_status_update',
                message
            )
        except Exception as e:
            logger.error(f"处理状态更新消息失败: {e}")
            message.reject(requeue=True)
    
    def _on_progress_update_message(self, body, message):
        """处理进度更新消息"""
        try:
            message_data = self._parse_message_body(body)
            if not message_data:
                message.reject(requeue=False)
                return
            
            logger.debug(f"收到进度更新消息: job_id={message_data.get('job_id')}, progress={message_data.get('progress')}")
            # 直接处理消息（异步执行，不阻塞）
            self._process_message_async(
                handle_job_progress_update,
                message_data,
                'job_progress_update',
                message
            )
        except Exception as e:
            logger.error(f"处理进度更新消息失败: {e}")
            message.reject(requeue=True)
    
    def _on_result_message(self, body, message):
        """处理结果数据消息"""
        try:
            message_data = self._parse_message_body(body)
            if not message_data:
                message.reject(requeue=False)
                return
            
            logger.debug(f"收到结果消息: job_id={message_data.get('job_id')}")
            # 直接处理消息（异步执行，不阻塞）
            self._process_message_async(
                handle_job_result,
                message_data,
                'job_result',
                message
            )
        except Exception as e:
            logger.error(f"处理结果消息失败: {e}")
            message.reject(requeue=True)
    
    def _on_failure_message(self, body, message):
        """处理失败消息"""
        try:
            message_data = self._parse_message_body(body)
            if not message_data:
                message.reject(requeue=False)
                return
            
            logger.debug(f"收到失败消息: job_id={message_data.get('job_id')}")
            # 直接处理消息（异步执行，不阻塞）
            self._process_message_async(
                handle_job_failure,
                message_data,
                'job_failure',
                message
            )
        except Exception as e:
            logger.error(f"处理失败消息失败: {e}")
            message.reject(requeue=True)
    
    def start_consuming(self):
        """开始消费消息"""
        if self._running:
            logger.warning("消息消费者已在运行")
            return
        
        self._running = True
        logger.info("启动消息消费者...")
        
        try:
            # 直接使用Connection而不是连接池（与message_publisher保持一致）
            with Connection(self.broker_url) as conn:
                # 创建队列
                queues = {
                    'status': Queue(
                        messaging_config.QUEUE_STATUS_UPDATES,
                        exchange=self.exchange,
                        routing_key=messaging_config.ROUTING_KEY_STATUS_UPDATE,
                        **messaging_config.get_queue_config(messaging_config.QUEUE_STATUS_UPDATES)
                    ),
                    'progress': Queue(
                        messaging_config.QUEUE_PROGRESS_UPDATES,
                        exchange=self.exchange,
                        routing_key=messaging_config.ROUTING_KEY_PROGRESS_UPDATE,
                        **messaging_config.get_queue_config(messaging_config.QUEUE_PROGRESS_UPDATES)
                    ),
                    'result': Queue(
                        messaging_config.QUEUE_RESULTS,
                        exchange=self.exchange,
                        routing_key=messaging_config.ROUTING_KEY_RESULT,
                        **messaging_config.get_queue_config(messaging_config.QUEUE_RESULTS)
                    ),
                    'failure': Queue(
                        messaging_config.QUEUE_FAILURES,
                        exchange=self.exchange,
                        routing_key=messaging_config.ROUTING_KEY_FAILURE,
                        **messaging_config.get_queue_config(messaging_config.QUEUE_FAILURES)
                    ),
                }
                
                # 声明交换器和队列
                self.exchange.declare(channel=conn.default_channel)
                for queue in queues.values():
                    try:
                        queue.declare(channel=conn.default_channel)
                    except ChannelError as e:
                        # 如果队列已存在但参数不匹配（如缺少 x-max-priority）
                        error_str = str(e)
                        if "PRECONDITION_FAILED" in error_str or "inequivalent arg" in error_str:
                            logger.warning(
                                f"队列 '{queue.name}' 已存在但参数不匹配: {e}。"
                                f"将使用现有队列（优先级功能可能不可用）。"
                                f"如需启用优先级，请手动删除队列后重启服务。"
                            )
                            # 使用被动模式声明队列（只检查是否存在，不修改参数）
                            try:
                                queue.declare(channel=conn.default_channel, passive=True)
                                logger.info(f"队列 '{queue.name}' 已存在，继续使用")
                            except Exception as passive_e:
                                logger.error(f"无法使用被动模式声明队列 '{queue.name}': {passive_e}")
                                raise
                        else:
                            # 其他类型的 ChannelError，重新抛出
                            raise
                
                # 创建消费者
                consumers = [
                    Consumer(
                        conn,
                        queues['status'],
                        callbacks=[self._on_status_update_message],
                        accept=['json']
                    ),
                    Consumer(
                        conn,
                        queues['progress'],
                        callbacks=[self._on_progress_update_message],
                        accept=['json']
                    ),
                    Consumer(
                        conn,
                        queues['result'],
                        callbacks=[self._on_result_message],
                        accept=['json']
                    ),
                    Consumer(
                        conn,
                        queues['failure'],
                        callbacks=[self._on_failure_message],
                        accept=['json']
                    ),
                ]
                
                self._consumers = consumers
                
                # 开始消费
                logger.info("消息消费者已启动，开始监听消息...")
                for consumer in consumers:
                    consumer.consume()
                
                # 持续监听
                while self._running:
                    try:
                        conn.drain_events(timeout=1)
                    except (socket.timeout, KombuTimeoutError, TimeoutError) as e:
                        # 超时是正常行为，当没有消息到达时会超时
                        # 不需要记录错误，继续循环即可
                        continue
                    except Exception as e:
                        # 真正的错误才记录
                        if self._running:
                            logger.error(f"消费消息时出错: {e}", exc_info=True)
                            # 短暂等待后继续，避免快速重试导致日志刷屏
                            time.sleep(1)
                        
        except KeyboardInterrupt:
            logger.info("收到停止信号，正在关闭消息消费者...")
            self.stop_consuming()
        except Exception as e:
            logger.error(f"消息消费者运行出错: {e}")
            self._running = False
            raise
    
    def stop_consuming(self):
        """停止消费消息"""
        logger.info("正在停止消息消费者...")
        self._running = False
        
        for consumer in self._consumers:
            try:
                consumer.cancel()
            except Exception as e:
                logger.error(f"取消消费者时出错: {e}")
        
        self._consumers = []
        
        # 关闭线程池
        if self._executor:
            self._executor.shutdown(wait=True)
            logger.info("消息处理线程池已关闭")
        
        # 连接会在with语句中自动关闭，这里不需要额外操作
        logger.info("消息消费者已停止")


def get_message_consumer() -> MessageConsumer:
    """获取消息消费者实例"""
    return MessageConsumer()

