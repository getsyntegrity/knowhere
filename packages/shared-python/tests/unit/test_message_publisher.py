"""
消息发布服务单元测试
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from shared.services.messaging import MessagePublisher
from shared.models.schemas.messages import (
    JobStatusUpdateMessage,
    JobProgressUpdateMessage,
    JobResultMessage,
    JobFailureMessage,
)


class TestMessagePublisher:
    """消息发布器测试类"""
    
    @pytest.fixture
    def publisher(self):
        """创建消息发布器实例"""
        return MessagePublisher()
    
    @patch('app.services.messaging.message_publisher.connections')
    @patch('app.services.messaging.message_publisher.Producer')
    @patch('app.services.messaging.message_publisher.Queue')
    def test_publish_status_update_success(self, mock_queue, mock_producer, mock_connections, publisher):
        """测试发布状态更新消息成功"""
        # 模拟连接和队列
        mock_conn = MagicMock()
        mock_connections.__getitem__.return_value.acquire.return_value.__enter__.return_value = mock_conn
        mock_queue_instance = MagicMock()
        mock_queue.return_value = mock_queue_instance
        mock_queue_instance.bind.return_value.declare = MagicMock()
        
        mock_prod = MagicMock()
        mock_producer.return_value = mock_prod
        
        # 执行发布
        result = publisher.publish_status_update(
            job_id="test_job_123",
            status="running",
            trigger="start_processing",
            previous_status="pending",
            async_mode=False
        )
        
        # 验证结果
        assert result is True
        mock_prod.publish.assert_called_once()
        call_args = mock_prod.publish.call_args
        assert call_args[1]['routing_key'] == 'job.status.update'
    
    @patch('app.services.messaging.message_publisher.Connection')
    def test_publish_status_update_failure(self, mock_connection_class, publisher):
        """测试发布状态更新消息失败"""
        # 模拟连接失败（在with语句的__enter__中抛出异常）
        mock_conn_instance = MagicMock()
        mock_conn_instance.__enter__.side_effect = Exception("Connection failed")
        mock_conn_instance.__exit__ = MagicMock(return_value=None)
        mock_connection_class.return_value = mock_conn_instance
        
        # 执行发布
        result = publisher.publish_status_update(
            job_id="test_job_123",
            status="running",
            trigger="start_processing",
            async_mode=False
        )
        
        # 验证失败时返回False
        assert result is False
    
    @patch('app.services.messaging.message_publisher.connections')
    @patch('app.services.messaging.message_publisher.Producer')
    @patch('app.services.messaging.message_publisher.Queue')
    def test_publish_progress_update(self, mock_queue, mock_producer, mock_connections, publisher):
        """测试发布进度更新消息"""
        # 模拟连接和队列
        mock_conn = MagicMock()
        mock_connections.__getitem__.return_value.acquire.return_value.__enter__.return_value = mock_conn
        mock_queue_instance = MagicMock()
        mock_queue.return_value = mock_queue_instance
        mock_queue_instance.bind.return_value.declare = MagicMock()
        
        mock_prod = MagicMock()
        mock_producer.return_value = mock_prod
        
        # 执行发布
        result = publisher.publish_progress_update(
            job_id="test_job_123",
            progress=50,
            message_text="处理中...",
            async_mode=False
        )
        
        # 验证结果
        assert result is True
        mock_prod.publish.assert_called_once()
    
    @patch('app.services.messaging.message_publisher.connections')
    @patch('app.services.messaging.message_publisher.Producer')
    @patch('app.services.messaging.message_publisher.Queue')
    def test_publish_result(self, mock_queue, mock_producer, mock_connections, publisher):
        """测试发布结果消息"""
        # 模拟连接和队列
        mock_conn = MagicMock()
        mock_connections.__getitem__.return_value.acquire.return_value.__enter__.return_value = mock_conn
        mock_queue_instance = MagicMock()
        mock_queue.return_value = mock_queue_instance
        mock_queue_instance.bind.return_value.declare = MagicMock()
        
        mock_prod = MagicMock()
        mock_producer.return_value = mock_prod
        
        # 执行发布
        result = publisher.publish_result(
            job_id="test_job_123",
            chunks_job_id="test_job_123",
            result_s3_key="s3://bucket/key.zip",
            checksum="abc123",
            zip_size=1024,
            stored_count=10,
            async_mode=False
        )
        
        # 验证结果
        assert result is True
        mock_prod.publish.assert_called_once()
        call_args = mock_prod.publish.call_args
        message_data = call_args[0][0]
        assert message_data['job_id'] == "test_job_123"
        assert message_data['result_s3_key'] == "s3://bucket/key.zip"
    
    @patch('app.services.messaging.message_publisher.connections')
    @patch('app.services.messaging.message_publisher.Producer')
    @patch('app.services.messaging.message_publisher.Queue')
    def test_publish_failure(self, mock_queue, mock_producer, mock_connections, publisher):
        """测试发布失败消息"""
        # 模拟连接和队列
        mock_conn = MagicMock()
        mock_connections.__getitem__.return_value.acquire.return_value.__enter__.return_value = mock_conn
        mock_queue_instance = MagicMock()
        mock_queue.return_value = mock_queue_instance
        mock_queue_instance.bind.return_value.declare = MagicMock()
        
        mock_prod = MagicMock()
        mock_producer.return_value = mock_prod
        
        # 执行发布
        result = publisher.publish_failure(
            job_id="test_job_123",
            error_message="Test error",
            error_type="ValueError",
            stack_trace="Traceback...",
            async_mode=False
        )
        
        # 验证结果
        assert result is True
        mock_prod.publish.assert_called_once()
        call_args = mock_prod.publish.call_args
        message_data = call_args[0][0]
        assert message_data['error_message'] == "Test error"
        assert message_data['error_type'] == "ValueError"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

