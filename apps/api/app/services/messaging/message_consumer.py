"""
消息消费者服务
监听RabbitMQ队列并触发相应的Celery任务
"""
import json
import socket
import time

from kombu import Connection, Consumer, Exchange, Queue
from kombu.exceptions import TimeoutError as KombuTimeoutError
from loguru import logger

from app.core.celery_app import get_celery_app
from app.core.config import app_config
from app.core.config.messaging import messaging_config


class MessageConsumer:
    """消息消费者 - 监听RabbitMQ队列并触发Celery任务"""
    
    def __init__(self):
        """初始化消息消费者"""
        self.broker_url = app_config.get_rabbitmq_url()
        self.exchange = Exchange(
            messaging_config.EXCHANGE_NAME,
            type=messaging_config.EXCHANGE_TYPE,
            durable=True
        )
        self.celery_app = get_celery_app()
        self._consumers = []
        self._running = False
    
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
    
    def _on_status_update_message(self, body, message):
        """处理状态更新消息"""
        try:
            message_data = self._parse_message_body(body)
            if not message_data:
                message.reject(requeue=False)
                return
            
            logger.debug(f"收到状态更新消息: job_id={message_data.get('job_id')}")
            # 触发Celery任务（注意：实际路径是 app.services.messaging.message_handlers）
            task = self.celery_app.send_task(
                'app.services.messaging.message_handlers.handle_job_status_update',
                args=[message_data],
                queue='kb_medium'
            )
            logger.info(f"状态更新任务已提交: task_id={task.id}, job_id={message_data.get('job_id')}")
            message.ack()
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
            # 触发Celery任务（注意：实际路径是 app.services.messaging.message_handlers）
            task = self.celery_app.send_task(
                'app.services.messaging.message_handlers.handle_job_progress_update',
                args=[message_data],
                queue='kb_medium'
            )
            logger.debug(f"进度更新任务已提交: task_id={task.id}, job_id={message_data.get('job_id')}")
            message.ack()
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
            # 触发Celery任务（注意：实际路径是 app.services.messaging.message_handlers）
            task = self.celery_app.send_task(
                'app.services.messaging.message_handlers.handle_job_result',
                args=[message_data],
                queue='kb_medium'
            )
            logger.info(f"结果处理任务已提交: task_id={task.id}, job_id={message_data.get('job_id')}")
            message.ack()
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
            # 触发Celery任务（注意：实际路径是 app.services.messaging.message_handlers）
            task = self.celery_app.send_task(
                'app.services.messaging.message_handlers.handle_job_failure',
                args=[message_data],
                queue='kb_medium'
            )
            logger.info(f"失败处理任务已提交: task_id={task.id}, job_id={message_data.get('job_id')}")
            message.ack()
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
                    queue.declare(channel=conn.default_channel)
                
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
        
        # 连接会在with语句中自动关闭，这里不需要额外操作
        logger.info("消息消费者已停止")


def get_message_consumer() -> MessageConsumer:
    """获取消息消费者实例"""
    return MessageConsumer()

