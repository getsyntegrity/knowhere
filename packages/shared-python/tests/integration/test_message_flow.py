"""
消息流集成测试
测试从Worker发布消息到API服务处理的完整流程
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime

from shared.services.messaging import MessagePublisher
from shared.services.messaging.message_handlers import (
    handle_job_status_update,
    handle_job_progress_update,
    handle_job_result,
    handle_job_failure,
)


class TestMessageFlow:
    """消息流集成测试类"""
    
    @pytest.fixture
    def publisher(self):
        """创建消息发布器实例"""
        return MessagePublisher()
    
    @pytest.mark.asyncio
    @patch('app.services.messaging.message_publisher.connections')
    @patch('app.services.messaging.message_publisher.Producer')
    @patch('app.services.messaging.message_publisher.Queue')
    @patch('app.services.messaging.message_handlers.get_db_context')
    @patch('app.services.messaging.message_handlers.JobStateMachine')
    async def test_status_update_flow(
        self,
        mock_state_machine,
        mock_db_context,
        mock_queue,
        mock_producer,
        mock_connections,
        publisher
    ):
        """测试状态更新完整流程"""
        # 模拟消息发布
        mock_conn = MagicMock()
        mock_connections.__getitem__.return_value.acquire.return_value.__enter__.return_value = mock_conn
        mock_queue_instance = MagicMock()
        mock_queue.return_value = mock_queue_instance
        mock_queue_instance.bind.return_value.declare = MagicMock()
        
        mock_prod = MagicMock()
        mock_producer.return_value = mock_prod
        
        # 模拟消息处理
        mock_db = AsyncMock()
        mock_db_context.return_value.__aenter__.return_value = mock_db
        
        mock_sm = MagicMock()
        mock_state_machine.return_value = mock_sm
        mock_sm.transition = AsyncMock(return_value=True)
        
        # 1. Worker发布状态更新消息
        publish_result = publisher.publish_status_update(
            job_id="test_job_123",
            status="running",
            trigger="start_processing",
            previous_status="pending",
            async_mode=False
        )
        
        assert publish_result is True
        
        # 2. 模拟消息被消费并处理
        message_data = {
            "job_id": "test_job_123",
            "status": "running",
            "trigger": "start_processing",
            "previous_status": "pending",
            "timestamp": datetime.utcnow().isoformat(),
            "message_type": "job_status_update"
        }
        
        # 3. API服务处理消息（直接调用异步函数）
        result = await handle_job_status_update(message_data)
        assert result['status'] == 'success'
        assert result['job_id'] == "test_job_123"
    
    @pytest.mark.asyncio
    @patch('app.services.messaging.message_publisher.connections')
    @patch('app.services.messaging.message_publisher.Producer')
    @patch('app.services.messaging.message_publisher.Queue')
    @patch('app.services.messaging.message_handlers.RedisServiceFactory')
    @patch('app.services.messaging.message_handlers.TaskRedisService')
    async def test_progress_update_flow(
        self,
        mock_task_service,
        mock_redis_factory,
        mock_queue,
        mock_producer,
        mock_connections,
        publisher
    ):
        """测试进度更新完整流程"""
        # 模拟消息发布
        mock_conn = MagicMock()
        mock_connections.__getitem__.return_value.acquire.return_value.__enter__.return_value = mock_conn
        mock_queue_instance = MagicMock()
        mock_queue.return_value = mock_queue_instance
        mock_queue_instance.bind.return_value.declare = MagicMock()
        
        mock_prod = MagicMock()
        mock_producer.return_value = mock_prod
        
        # 模拟消息处理
        mock_redis_service = MagicMock()
        mock_redis_factory.get_service.return_value = mock_redis_service
        
        mock_task_svc = MagicMock()
        mock_task_service.return_value = mock_task_svc
        mock_task_svc.update_task_progress = AsyncMock(return_value=True)
        
        # 1. Worker发布进度更新消息
        publish_result = publisher.publish_progress_update(
            job_id="test_job_123",
            progress=50,
            message_text="处理中...",
            async_mode=False
        )
        
        assert publish_result is True
        
        # 2. 模拟消息被消费并处理
        message_data = {
            "job_id": "test_job_123",
            "progress": 50,
            "message": "处理中...",
            "timestamp": datetime.utcnow().isoformat(),
            "message_type": "job_progress_update"
        }
        
        # 3. API服务处理消息（直接调用异步函数）
        result = await handle_job_progress_update(message_data)
        assert result['status'] == 'success'
        assert result['progress'] == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

