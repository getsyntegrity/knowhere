"""
消息发布服务
封装RabbitMQ消息发布逻辑
"""
import asyncio
import sys
from typing import Any, Dict, List, Optional

from kombu import Exchange, Producer, Queue
from kombu.exceptions import ChannelError
from loguru import logger

# 增加整数字符串转换限制（用于处理大数字，如时间戳）
sys.set_int_max_str_digits(10000)

from app.core.config import app_config
from app.core.config.messaging import messaging_config
from app.models.schemas.messages import (
    BaseMessage,
    JobFailureMessage,
    JobProgressUpdateMessage,
    JobResultMessage,
    JobStatusUpdateMessage,
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
    
    def _publish_sync(
        self,
        message: BaseMessage,
        routing_key: str,
        queue_name: str,
        priority: Optional[int] = None
    ) -> bool:
        """
        同步发布消息
        
        Args:
            message: 消息对象
            routing_key: 路由键
            queue_name: 队列名称
            priority: 消息优先级（如果为None，则根据消息类型自动设置）
            
        Returns:
            bool: 是否发布成功
        """
        try:
            # 如果没有指定优先级，根据消息类型自动设置
            if priority is None:
                priority = messaging_config.get_message_priority(message.message_type)
            
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
                try:
                    queue.bind(conn).declare()
                except ChannelError as e:
                    # 如果队列已存在但参数不匹配（如缺少 x-max-priority）
                    error_str = str(e)
                    if "PRECONDITION_FAILED" in error_str or "inequivalent arg" in error_str:
                        logger.warning(
                            f"队列 '{queue_name}' 已存在但参数不匹配: {e}。"
                            f"将使用现有队列（优先级功能可能不可用）。"
                        )
                        # 使用被动模式声明队列（只检查是否存在，不修改参数）
                        try:
                            queue.bind(conn).declare(passive=True)
                        except Exception as passive_e:
                            logger.error(f"无法使用被动模式声明队列 '{queue_name}': {passive_e}")
                            raise
                    else:
                        # 其他类型的 ChannelError，重新抛出
                        raise
                
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
                
                # 发布消息，包含优先级
                producer.publish(
                    message_dict,
                    routing_key=routing_key,
                    delivery_mode=2,  # 直接使用固定值，避免类型问题
                    priority=priority,
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
        queue_name: str,
        priority: Optional[int] = None
    ) -> bool:
        """
        异步发布消息
        
        Args:
            message: 消息对象
            routing_key: 路由键
            queue_name: 队列名称
            priority: 消息优先级（如果为None，则根据消息类型自动设置）
            
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
            queue_name,
            priority
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
                priority = messaging_config.get_message_priority('job_status_update')
                if loop.is_running():
                    # 如果事件循环正在运行，使用run_in_executor
                    return asyncio.run_coroutine_threadsafe(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_STATUS_UPDATE,
                            messaging_config.QUEUE_STATUS_UPDATES,
                            priority
                        ),
                        loop
                    ).result(timeout=5)
                else:
                    return loop.run_until_complete(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_STATUS_UPDATE,
                            messaging_config.QUEUE_STATUS_UPDATES,
                            priority
                        )
                    )
            except Exception as e:
                logger.error(f"异步发布状态更新消息失败: {e}")
                # 降级为同步发布
                return self._publish_sync(
                    message,
                    messaging_config.ROUTING_KEY_STATUS_UPDATE,
                    messaging_config.QUEUE_STATUS_UPDATES,
                    messaging_config.get_message_priority('job_status_update')
                )
        else:
            return self._publish_sync(
                message,
                messaging_config.ROUTING_KEY_STATUS_UPDATE,
                messaging_config.QUEUE_STATUS_UPDATES,
                messaging_config.get_message_priority('job_status_update')
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
                priority = messaging_config.get_message_priority('job_progress_update')
                if loop.is_running():
                    return asyncio.run_coroutine_threadsafe(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_PROGRESS_UPDATE,
                            messaging_config.QUEUE_PROGRESS_UPDATES,
                            priority
                        ),
                        loop
                    ).result(timeout=5)
                else:
                    return loop.run_until_complete(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_PROGRESS_UPDATE,
                            messaging_config.QUEUE_PROGRESS_UPDATES,
                            priority
                        )
                    )
            except Exception as e:
                logger.error(f"异步发布进度更新消息失败: {e}")
                return self._publish_sync(
                    message,
                    messaging_config.ROUTING_KEY_PROGRESS_UPDATE,
                    messaging_config.QUEUE_PROGRESS_UPDATES,
                    messaging_config.get_message_priority('job_progress_update')
                )
        else:
            return self._publish_sync(
                message,
                messaging_config.ROUTING_KEY_PROGRESS_UPDATE,
                messaging_config.QUEUE_PROGRESS_UPDATES,
                messaging_config.get_message_priority('job_progress_update')
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
                priority = messaging_config.get_message_priority('job_result')
                if loop.is_running():
                    return asyncio.run_coroutine_threadsafe(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_RESULT,
                            messaging_config.QUEUE_RESULTS,
                            priority
                        ),
                        loop
                    ).result(timeout=10)  # 结果消息可能较大，增加超时
                else:
                    return loop.run_until_complete(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_RESULT,
                            messaging_config.QUEUE_RESULTS,
                            priority
                        )
                    )
            except Exception as e:
                logger.error(f"异步发布结果消息失败: {e}")
                return self._publish_sync(
                    message,
                    messaging_config.ROUTING_KEY_RESULT,
                    messaging_config.QUEUE_RESULTS,
                    messaging_config.get_message_priority('job_result')
                )
        else:
            return self._publish_sync(
                message,
                messaging_config.ROUTING_KEY_RESULT,
                messaging_config.QUEUE_RESULTS,
                messaging_config.get_message_priority('job_result')
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
                priority = messaging_config.get_message_priority('job_failure')
                if loop.is_running():
                    return asyncio.run_coroutine_threadsafe(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_FAILURE,
                            messaging_config.QUEUE_FAILURES,
                            priority
                        ),
                        loop
                    ).result(timeout=5)
                else:
                    return loop.run_until_complete(
                        self._publish_async(
                            message,
                            messaging_config.ROUTING_KEY_FAILURE,
                            messaging_config.QUEUE_FAILURES,
                            priority
                        )
                    )
            except Exception as e:
                logger.error(f"异步发布失败消息失败: {e}")
                return self._publish_sync(
                    message,
                    messaging_config.ROUTING_KEY_FAILURE,
                    messaging_config.QUEUE_FAILURES,
                    messaging_config.get_message_priority('job_failure')
                )
        else:
            return self._publish_sync(
                message,
                messaging_config.ROUTING_KEY_FAILURE,
                messaging_config.QUEUE_FAILURES,
                messaging_config.get_message_priority('job_failure')
            )


def get_message_publisher() -> MessagePublisher:
    """获取消息发布器实例"""
    return MessagePublisher()

