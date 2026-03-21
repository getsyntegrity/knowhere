"""
异步消息发布服务
使用aio-pika封装RabbitMQ消息发布逻辑
"""
import asyncio
import json
import sys
import threading
from typing import Any, Dict, List, Optional

import aio_pika
from aio_pika import DeliveryMode
from loguru import logger

# 增加整数字符串转换限制（用于处理大数字，如时间戳）
sys.set_int_max_str_digits(10000)

from shared.core.config.messaging import messaging_config
from shared.models.schemas.messages import (
    BaseMessage,
    JobFailureMessage,
    JobProgressUpdateMessage,
    JobResultMessage,
)
from shared.services.messaging.async_config import (
    get_exchange_config,
    get_message_properties,
    get_queue_config,
    get_queue_name,
    get_routing_key,
)
from shared.services.messaging.async_connection import get_connection_manager
from shared.services.messaging.monitoring import message_monitoring


class MessagePublisher:
    """异步消息发布器 - 使用aio-pika封装RabbitMQ消息发布"""
    
    def __init__(self):
        """初始化消息发布器"""
        self._connection_manager = get_connection_manager()
        self._exchange: Optional[aio_pika.Exchange] = None
        self._initialized = False
    
    async def _ensure_initialized(self):
        """确保交换器和队列已初始化"""
        if self._initialized:
            logger.debug("消息发布器已初始化，跳过")
            return
        
        try:
            logger.debug("步骤1: 获取通道")
            # get_channel()内部已经有超时处理，这里不需要再设置超时
            # connect()有30秒超时，channel创建有5秒超时
            channel = await self._connection_manager.get_channel()
            logger.debug(f"通道获取成功: channel_closed={channel.is_closed}")
            
            # 声明交换器
            logger.debug("步骤2: 声明交换器")
            exchange_config = get_exchange_config()
            self._exchange = await asyncio.wait_for(
                channel.declare_exchange(
                exchange_config["name"],
                exchange_config["type"],
                durable=exchange_config["durable"],
                auto_delete=exchange_config["auto_delete"],
                ),
                timeout=10.0
            )
            logger.debug(f"交换器声明成功: exchange={exchange_config['name']}")
            
            self._initialized = True
            logger.debug("消息发布器已初始化")
            
        except asyncio.TimeoutError as e:
            logger.error(f"初始化消息发布器超时: {e}")
            raise
        except Exception as e:
            logger.error(f"初始化消息发布器失败: {e}", exc_info=True)
            raise
    
    async def _publish(
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
        try:
            logger.debug(f"开始发布消息: type={message.message_type}, job_id={message.job_id}, routing_key={routing_key}, queue={queue_name}")
            
            logger.debug(f"步骤1: 确保初始化 - job_id={message.job_id}")
            # _ensure_initialized()内部已经有超时处理（connect 30秒，channel 5秒，exchange 10秒）
            # 总超时时间应该足够，这里设置35秒以确保连接建立和初始化完成
            await asyncio.wait_for(self._ensure_initialized(), timeout=35.0)
            logger.debug(f"初始化完成 - job_id={message.job_id}")
            
            # 如果没有指定优先级，根据消息类型自动设置
            if priority is None:
                priority = messaging_config.get_message_priority(message.message_type)
            logger.debug(f"消息优先级: job_id={message.job_id}, priority={priority}")
            
            # 确保队列存在
            logger.debug(f"步骤2: 获取通道 - job_id={message.job_id}")
            # get_channel()内部已经有超时处理，这里不需要再设置超时
            channel = await self._connection_manager.get_channel()
            logger.debug(f"通道获取成功 - job_id={message.job_id}, channel_closed={channel.is_closed}")
            
            queue_config = get_queue_config(queue_name)
            logger.debug(f"步骤3: 声明队列 - job_id={message.job_id}, queue={queue_name}")
            queue = await asyncio.wait_for(
                channel.declare_queue(
                queue_name,
                durable=queue_config["durable"],
                auto_delete=queue_config["auto_delete"],
                exclusive=queue_config["exclusive"],
                arguments=queue_config["arguments"],
                ),
                timeout=10.0
            )
            logger.debug(f"队列声明成功 - job_id={message.job_id}, queue={queue_name}")
            
            # 绑定队列到交换器
            logger.debug(f"步骤4: 绑定队列到交换器 - job_id={message.job_id}, routing_key={routing_key}")
            await asyncio.wait_for(
                queue.bind(self._exchange, routing_key=routing_key),
                timeout=10.0
            )
            logger.debug(f"队列绑定成功 - job_id={message.job_id}")
            
            # 序列化消息
            logger.debug(f"步骤5: 序列化消息 - job_id={message.job_id}")
            message_dict = message.model_dump(mode='json')
            message_body = json.dumps(message_dict).encode('utf-8')
            logger.debug(f"消息序列化完成 - job_id={message.job_id}, body_size={len(message_body)}")
            
            # 获取消息属性
            message_props = get_message_properties(priority=priority)
            
            # 转换delivery_mode为aio-pika的DeliveryMode枚举
            delivery_mode_value = message_props.get("delivery_mode", 2)
            if delivery_mode_value == 2:
                delivery_mode = DeliveryMode.PERSISTENT
            else:
                delivery_mode = DeliveryMode.NOT_PERSISTENT
            
            # 发布消息
            logger.debug(f"步骤6: 发布消息到交换器 - job_id={message.job_id}, routing_key={routing_key}")
            await asyncio.wait_for(
                self._exchange.publish(
                aio_pika.Message(
                    message_body,
                    delivery_mode=delivery_mode,
                    priority=message_props.get("priority"),
                    expiration=message_props.get("expiration"),
                ),
                routing_key=routing_key,
                ),
                timeout=10.0
            )
            logger.debug(f"消息发布成功: {message.message_type}, job_id={message.job_id}, routing_key={routing_key}")
            
            # 记录监控指标
            message_monitoring.record_message_published(
                message.message_type,
                message.job_id,
                True
            )
            
            return True
            
        except asyncio.TimeoutError as e:
            logger.error(
                f"消息发布超时: {message.message_type}, "
                f"job_id={message.job_id}, routing_key={routing_key}, queue={queue_name}, error={e}"
            )
            
            # 记录监控指标
            message_monitoring.record_message_published(
                message.message_type,
                message.job_id,
                False
            )
            
            return False
            
        except Exception as e:
            logger.error(
                f"消息发布失败: {message.message_type}, "
                f"job_id={message.job_id}, routing_key={routing_key}, queue={queue_name}, error={e}",
                exc_info=True
            )
            
            # 记录监控指标
            message_monitoring.record_message_published(
                message.message_type,
                message.job_id,
                False
            )
            
            return False
    
    async def publish_progress_update(
        self,
        job_id: str,
        progress: int,
        message_text: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        发布进度更新消息
        
        Args:
            job_id: 任务ID
            progress: 进度百分比 (0-100)
            message_text: 进度消息文本
            metadata: 元数据
            
        Returns:
            bool: 是否发布成功
        """
        message = JobProgressUpdateMessage(
            job_id=job_id,
            progress=progress,
            message=message_text,
            metadata=metadata
        )
        
        return await self._publish(
            message,
            get_routing_key('job_progress_update'),
            get_queue_name('job_progress_update')
        )
    
    async def publish_result(
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
        add_dir: Optional[str] = None
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
        
        return await self._publish(
            message,
            get_routing_key('job_result'),
            get_queue_name('job_result')
        )
    
    async def publish_failure(
        self,
        job_id: str,
        error_message: str,
        error_code: str = "UNKNOWN",
        error_type: Optional[str] = None,
        stack_trace: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        发布失败消息
        
        Args:
            job_id: 任务ID
            error_message: 错误消息
            error_code: 规范错误代码 (e.g., INVALID_ARGUMENT, INTERNAL_ERROR)
            error_type: 错误类型 (Python exception class name)
            stack_trace: 堆栈跟踪 (仅内部日志)
            metadata: 元数据
            
        Returns:
            bool: 是否发布成功
        """
        message = JobFailureMessage(
            job_id=job_id,
            error_code=error_code,
            error_message=error_message,
            error_type=error_type,
            stack_trace=stack_trace,
            metadata=metadata
        )
        
        return await self._publish(
            message,
            get_routing_key('job_failure'),
            get_queue_name('job_failure')
        )
    
    async def close(self):
        """关闭连接（清理资源）"""
        await self._connection_manager.close()
        self._initialized = False


# 全局消息发布器实例（延迟初始化）
_message_publisher: Optional[MessagePublisher] = None
_message_publisher_lock = threading.Lock()


def get_message_publisher() -> MessagePublisher:
    """获取消息发布器实例（单例模式）"""
    global _message_publisher
    if _message_publisher is None:
        with _message_publisher_lock:
            if _message_publisher is None:
                _message_publisher = MessagePublisher()
    return _message_publisher


def run_async_publish(coro):
    """
    在同步上下文中运行异步发布
    
    用于Celery任务等同步上下文中调用异步发布方法
    
    Args:
        coro: 异步协程对象
        
    Returns:
        协程的执行结果
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果事件循环正在运行，使用run_coroutine_threadsafe
            return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=30)
        else:
            # 如果没有运行的事件循环，使用run_until_complete
            return loop.run_until_complete(coro)
    except RuntimeError:
        # 如果没有事件循环，创建新的
        return asyncio.run(coro)
