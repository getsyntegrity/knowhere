"""
异步连接管理器
使用contextvars实现事件循环隔离，每个事件循环自动拥有独立的连接状态
无需锁，避免死锁问题
"""
import asyncio
from contextvars import ContextVar
from typing import Optional

import aio_pika
from aio_pika import Connection, Channel
from loguru import logger

from shared.services.messaging.async_config import get_connection_params

# 使用contextvars存储每个事件循环的连接状态
# contextvars自动隔离不同事件循环的上下文，无需手动管理锁
_connection_var: ContextVar[Optional[Connection]] = ContextVar('connection', default=None)
_channel_var: ContextVar[Optional[Channel]] = ContextVar('channel', default=None)


class AsyncConnectionManager:
    """
    异步连接管理器 - 无锁设计
    
    使用contextvars实现事件循环隔离：
    - 每个事件循环自动拥有独立的连接和通道
    - 无需锁，避免死锁问题
    - 代码更简洁，性能更好
    """
    
    def __init__(self):
        """
        初始化连接管理器
        
        注意：实际上不需要存储任何状态，所有状态都通过contextvars管理
        保留__init__方法以保持API兼容性
        """
        pass
    
    async def connect(self) -> Connection:
        """
        建立连接
        
        Returns:
            Connection对象
        """
        # 检查现有连接（contextvars自动隔离不同事件循环）
        connection = _connection_var.get()
        if connection and not connection.is_closed:
            logger.info("使用现有连接")
            return connection
        
        try:
            params = get_connection_params()
            if params["MESSAGE_BROKER_TYPE"] == "rabbitmq":
                connection = await asyncio.wait_for(
                    aio_pika.connect_robust(
                        host=params["host"],
                        port=params["port"],
                        login=params["login"],
                        password=params["password"],
                        virtualhost=params["virtualhost"],
                        client_properties=params.get("client_properties", {}),
                        heartbeat=params.get("heartbeat", 30),
                        blocked_connection_timeout=params.get("blocked_connection_timeout", 60),
                    ),
                    timeout=30.0
                )
            else:
                connection = await asyncio.wait_for(
                    aio_pika.connect_robust(
                        url=params["CELERY_BROKER_URL"],
                        client_properties=params.get("client_properties", {}),
                        heartbeat=params.get("heartbeat", 30),
                        blocked_connection_timeout=params.get("blocked_connection_timeout", 60),
                    ),
                    timeout=30.0
                )
            logger.info(f"正在连接到RabbitMQ: host={params['host']}, port={params['port']}, virtualhost={params['virtualhost']}")
            
            # 存储到当前上下文（自动绑定到当前事件循环）
            _connection_var.set(connection)
            logger.info(f"RabbitMQ连接已建立: connection_closed={connection.is_closed}")
            return connection
            
        except asyncio.TimeoutError as e:
            logger.error(f"连接RabbitMQ超时: {e}")
            raise
        except Exception as e:
            logger.error(f"连接RabbitMQ失败: {e}", exc_info=True)
            raise
    
    async def get_channel(self) -> Channel:
        """
        获取通道
        
        Returns:
            Channel对象
        """
        # 检查现有通道（contextvars自动隔离不同事件循环）
        channel = _channel_var.get()
        if channel and not channel.is_closed:
            logger.info("使用现有通道")
            return channel
        
        # 检查连接状态
        connection = _connection_var.get()
        if not connection or connection.is_closed:
            logger.info("连接不存在或已关闭，开始连接")
            connection = await self.connect()
        
        try:
            logger.info("开始创建新通道")
            channel = await asyncio.wait_for(
                connection.channel(),
                timeout=5.0
            )
            
            # 存储到当前上下文（自动绑定到当前事件循环）
            _channel_var.set(channel)
            logger.info(f"RabbitMQ通道已创建: channel_closed={channel.is_closed}")
            return channel
            
        except asyncio.TimeoutError as e:
            logger.error(f"创建RabbitMQ通道超时: {e}")
            raise
        except Exception as e:
            logger.error(f"创建RabbitMQ通道失败: {e}", exc_info=True)
            raise
    
    async def close(self):
        """
        关闭连接和通道
        
        注意：只关闭当前事件循环的连接和通道
        其他事件循环的连接不受影响（这是正确的行为）
        关闭后可以重新连接（通过调用connect()）
        """
        channel = _channel_var.get()
        if channel and not channel.is_closed:
            try:
                await channel.close()
                logger.debug("RabbitMQ通道已关闭")
            except Exception as e:
                logger.warning(f"关闭通道时出错: {e}")
            finally:
                _channel_var.set(None)
        
        connection = _connection_var.get()
        if connection and not connection.is_closed:
            try:
                await connection.close()
                logger.info("RabbitMQ连接已关闭")
            except Exception as e:
                logger.warning(f"关闭连接时出错: {e}")
            finally:
                _connection_var.set(None)
    
    async def health_check(self) -> bool:
        """
        健康检查
        
        Returns:
            连接是否健康
        """
        try:
            connection = _connection_var.get()
            if not connection or connection.is_closed:
                return False
            
            # 尝试获取通道来检查连接状态
            channel = await self.get_channel()
            return not channel.is_closed
            
        except Exception as e:
            logger.warning(f"健康检查失败: {e}")
            return False
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        connection = _connection_var.get()
        return (
            connection is not None
            and not connection.is_closed
        )


# 全局连接管理器实例
_connection_manager: Optional[AsyncConnectionManager] = None


def get_connection_manager() -> AsyncConnectionManager:
    """获取全局连接管理器实例（单例模式）"""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = AsyncConnectionManager()
    return _connection_manager

