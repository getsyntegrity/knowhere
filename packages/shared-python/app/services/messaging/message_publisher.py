"""
消息发布服务
封装RabbitMQ消息发布逻辑
"""
import json
import sys
import asyncio
from typing import Dict, Any, Optional, List
from kombu import Connection, Exchange, Queue, Producer
from kombu.pools import connections
from loguru import logger

# 增加整数字符串转换限制（用于处理大数字，如时间戳）
sys.set_int_max_str_digits(10000)

from app.core.config import app_config
from app.core.config.messaging import messaging_config
from app.models.schemas.messages import (
    BaseMessage,
    JobStatusUpdateMessage,
    JobProgressUpdateMessage,
    JobResultMessage,
    JobFailureMessage,
)
from app.services.messaging.monitoring import message_monitoring


class MessagePublisher:
    """消息发布器 - 封装RabbitMQ消息发布"""
    
    def __init__(self):
        """初始化消息发布器"""
        self.broker_url = app_config.get_rabbitmq_url()
        self.exchange = Exchange(
            messaging_config.EXCHANGE_NAME,
            type=messaging_config.EXCHANGE_TYPE,
            durable=True
        )
        self._connection_pool = None
    
    def close(self):
        """关闭连接池（清理资源）"""
        # 连接池会在with语句中自动关闭，这里不需要额外操作
        pass
    
    def _publish_sync(
        self,
        message: BaseMessage,
        routing_key: str,
        queue_name: str
    ) -> bool:
        """
        同步发布消息
        
        Args:
            message: 消息对象
            routing_key: 路由键
            queue_name: 队列名称
            
        Returns:
            bool: 是否发布成功
        """
        try:
            # 确保队列存在
            queue = Queue(
                queue_name,
                exchange=self.exchange,
                routing_key=routing_key,
                **messaging_config.get_queue_config(queue_name)
            )
            
            # 直接使用Connection而不是连接池（简化实现）
            from kombu import Connection
            with Connection(self.broker_url) as conn:
                # 绑定队列到交换器
                queue.bind(conn).declare()
                
                # 创建生产者
                producer = Producer(
                    conn,
                    exchange=self.exchange,
                    routing_key=routing_key,
                    serializer='json'
                )
                
                # 序列化消息（使用json模式确保所有类型正确序列化）
                message_dict = message.model_dump(mode='json')
                # timestamp已经在model_dump中序列化为ISO格式字符串
                
                # 发布消息
                # 简化：只使用必要的参数，避免kombu内部类型转换问题
                producer.publish(
                    message_dict,
                    routing_key=routing_key,
                    delivery_mode=2,  # 直接使用固定值，避免类型问题
                )
                
                logger.debug(f"消息发布成功: {message.message_type}, job_id={message.job_id}, routing_key={routing_key}")
                
                # 记录监控指标
                message_monitoring.record_message_published(
                    message.message_type,
                    message.job_id,
                    True
                )
                
                return True
                
        except Exception as e:
            logger.error(f"消息发布失败: {message.message_type}, job_id={message.job_id}, error={e}")
            
            # 记录监控指标
            message_monitoring.record_message_published(
                message.message_type,
                message.job_id,
                False
            )
            
            return False
    
    async def _publish_async(
        self,
        message: BaseMessage,
        routing_key: str,
        queue_name: str
    ) -> bool:
        """
        异步发布消息
        
        Args:
            message: 消息对象
            routing_key: 路由键
            queue_name: 队列名称
            
        Returns:
            bool: 是否发布成功
        """
        # 在线程池中执行同步发布
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._publish_sync,
            message,
            routing_key,
            queue_name
        )
    
    def publish_status_update(
        self,
        job_id: str,
        status: str,
        trigger: str,
        previous_status: Optional[str] = None,
        operator_id: Optional[str] = None,
        operator_type: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
        async_mode: bool = True
    ) -> bool:
        """
        发布状态更新消息
        
        Args:
            job_id: 任务ID
            status: 新状态
            trigger: 触发原因
            previous_status: 之前的状态
            operator_id: 操作者ID
            operator_type: 操作者类型
            metadata: 元数据
            async_mode: 是否异步发布
            
        Returns:
            bool: 是否发布成功
        """
        message = JobStatusUpdateMessage(
            job_id=job_id,
            status=status,
            previous_status=previous_status,
            trigger=trigger,
            operator_id=operator_id,
            operator_type=operator_type,
            metadata=metadata
        )
        
        if async_mode:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果事件循环正在运行，使用run_in_executor
                    return asyncio.run_coroutine_threadsafe(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_STATUS_UPDATE,
                            messaging_config.QUEUE_STATUS_UPDATES
                        ),
                        loop
                    ).result(timeout=5)
                else:
                    return loop.run_until_complete(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_STATUS_UPDATE,
                            messaging_config.QUEUE_STATUS_UPDATES
                        )
                    )
            except Exception as e:
                logger.error(f"异步发布状态更新消息失败: {e}")
                # 降级为同步发布
                return self._publish_sync(
                    message,
                    messaging_config.ROUTING_KEY_STATUS_UPDATE,
                    messaging_config.QUEUE_STATUS_UPDATES
                )
        else:
            return self._publish_sync(
                message,
                messaging_config.ROUTING_KEY_STATUS_UPDATE,
                messaging_config.QUEUE_STATUS_UPDATES
            )
    
    def publish_progress_update(
        self,
        job_id: str,
        progress: int,
        message_text: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        async_mode: bool = True
    ) -> bool:
        """
        发布进度更新消息
        
        Args:
            job_id: 任务ID
            progress: 进度百分比 (0-100)
            message_text: 进度消息文本
            metadata: 元数据
            async_mode: 是否异步发布
            
        Returns:
            bool: 是否发布成功
        """
        message = JobProgressUpdateMessage(
            job_id=job_id,
            progress=progress,
            message=message_text,
            metadata=metadata
        )
        
        if async_mode:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    return asyncio.run_coroutine_threadsafe(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_PROGRESS_UPDATE,
                            messaging_config.QUEUE_PROGRESS_UPDATES
                        ),
                        loop
                    ).result(timeout=5)
                else:
                    return loop.run_until_complete(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_PROGRESS_UPDATE,
                            messaging_config.QUEUE_PROGRESS_UPDATES
                        )
                    )
            except Exception as e:
                logger.error(f"异步发布进度更新消息失败: {e}")
                return self._publish_sync(
                    message,
                    messaging_config.ROUTING_KEY_PROGRESS_UPDATE,
                    messaging_config.QUEUE_PROGRESS_UPDATES
                )
        else:
            return self._publish_sync(
                message,
                messaging_config.ROUTING_KEY_PROGRESS_UPDATE,
                messaging_config.QUEUE_PROGRESS_UPDATES
            )
    
    def publish_result(
        self,
        job_id: str,
        chunks_job_id: str,
        result_s3_key: str,
        checksum: str,
        zip_size: int,
        stored_count: int = 0,
        kb_records: Optional[List[Dict[str, Any]]] = None,
        statistics: Optional[Dict[str, Any]] = None,
        delivery_mode: str = "url",
        add_dir: Optional[str] = None,
        async_mode: bool = True
    ) -> bool:
        """
        发布结果数据消息
        
        Args:
            job_id: 任务ID
            chunks_job_id: Chunks数据关联的job_id
            result_s3_key: 结果ZIP包的S3键
            checksum: 文件校验和
            zip_size: ZIP文件大小
            stored_count: 存储的记录数量
            kb_records: 知识库记录列表
            statistics: 统计信息
            delivery_mode: 交付模式
            add_dir: 处理结果目录路径
            async_mode: 是否异步发布
            
        Returns:
            bool: 是否发布成功
        """
        message = JobResultMessage(
            job_id=job_id,
            chunks_job_id=chunks_job_id,
            result_s3_key=result_s3_key,
            checksum=checksum,
            zip_size=zip_size,
            stored_count=stored_count,
            kb_records=kb_records,
            statistics=statistics,
            delivery_mode=delivery_mode,
            add_dir=add_dir
        )
        
        if async_mode:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    return asyncio.run_coroutine_threadsafe(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_RESULT,
                            messaging_config.QUEUE_RESULTS
                        ),
                        loop
                    ).result(timeout=10)  # 结果消息可能较大，增加超时
                else:
                    return loop.run_until_complete(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_RESULT,
                            messaging_config.QUEUE_RESULTS
                        )
                    )
            except Exception as e:
                logger.error(f"异步发布结果消息失败: {e}")
                return self._publish_sync(
                    message,
                    messaging_config.ROUTING_KEY_RESULT,
                    messaging_config.QUEUE_RESULTS
                )
        else:
            return self._publish_sync(
                message,
                messaging_config.ROUTING_KEY_RESULT,
                messaging_config.QUEUE_RESULTS
            )
    
    def publish_failure(
        self,
        job_id: str,
        error_message: str,
        error_type: Optional[str] = None,
        stack_trace: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        async_mode: bool = True
    ) -> bool:
        """
        发布失败消息
        
        Args:
            job_id: 任务ID
            error_message: 错误消息
            error_type: 错误类型
            stack_trace: 堆栈跟踪
            metadata: 元数据
            async_mode: 是否异步发布
            
        Returns:
            bool: 是否发布成功
        """
        message = JobFailureMessage(
            job_id=job_id,
            error_message=error_message,
            error_type=error_type,
            stack_trace=stack_trace,
            metadata=metadata
        )
        
        if async_mode:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    return asyncio.run_coroutine_threadsafe(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_FAILURE,
                            messaging_config.QUEUE_FAILURES
                        ),
                        loop
                    ).result(timeout=5)
                else:
                    return loop.run_until_complete(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_FAILURE,
                            messaging_config.QUEUE_FAILURES
                        )
                    )
            except Exception as e:
                logger.error(f"异步发布失败消息失败: {e}")
                return self._publish_sync(
                    message,
                    messaging_config.ROUTING_KEY_FAILURE,
                    messaging_config.QUEUE_FAILURES
                )
        else:
            return self._publish_sync(
                message,
                messaging_config.ROUTING_KEY_FAILURE,
                messaging_config.QUEUE_FAILURES
            )


def get_message_publisher() -> MessagePublisher:
    """获取消息发布器实例"""
    return MessagePublisher()

