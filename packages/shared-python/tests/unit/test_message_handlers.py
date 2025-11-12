"""
消息处理器单元测试
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime

from shared.services.messaging.message_handlers import (
    handle_job_status_update,
    handle_job_progress_update,
    handle_job_result,
    handle_job_failure,
    _handle_status_update_async,
    _handle_progress_update_async,
    _handle_result_async,
    _handle_failure_async,
)
from shared.models.schemas.messages import (
    JobStatusUpdateMessage,
    JobProgressUpdateMessage,
    JobResultMessage,
    JobFailureMessage,
)


class TestMessageHandlers:
    """消息处理器测试类"""
    
    @pytest.mark.asyncio
    @patch('app.services.messaging.message_handlers.get_db_context')
    @patch('app.services.messaging.message_handlers.JobStateMachine')
    async def test_handle_status_update_success(self, mock_state_machine, mock_db_context):
        """测试处理状态更新消息成功"""
        # 模拟数据库上下文
        mock_db = AsyncMock()
        mock_db_context.return_value.__aenter__.return_value = mock_db
        
        # 模拟状态机
        mock_sm = MagicMock()
        mock_state_machine.return_value = mock_sm
        mock_sm.transition = AsyncMock(return_value=True)
        
        # 创建消息
        message = JobStatusUpdateMessage(
            job_id="test_job_123",
            status="running",
            trigger="start_processing",
            previous_status="pending"
        )
        
        # 执行处理
        result = await _handle_status_update_async(message)
        
        # 验证结果
        assert result['status'] == 'success'
        assert result['job_id'] == "test_job_123"
        mock_sm.transition.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.services.messaging.message_handlers.RedisServiceFactory')
    @patch('app.services.messaging.message_handlers.TaskRedisService')
    async def test_handle_progress_update_success(self, mock_task_service, mock_redis_factory):
        """测试处理进度更新消息成功"""
        # 模拟Redis服务
        mock_redis_service = MagicMock()
        mock_redis_factory.get_service.return_value = mock_redis_service
        
        # 模拟任务服务
        mock_task_svc = MagicMock()
        mock_task_service.return_value = mock_task_svc
        mock_task_svc.update_task_progress = AsyncMock(return_value=True)
        
        # 创建消息
        message = JobProgressUpdateMessage(
            job_id="test_job_123",
            progress=50,
            message="处理中..."
        )
        
        # 执行处理
        result = await _handle_progress_update_async(message)
        
        # 验证结果
        assert result['status'] == 'success'
        assert result['progress'] == 50
        mock_task_svc.update_task_progress.assert_called_once_with(
            "test_job_123", 50, "处理中..."
        )
    
    @pytest.mark.asyncio
    @patch('app.services.messaging.message_handlers.get_db_context')
    @patch('app.services.messaging.message_handlers.create_update_kb')
    @patch('app.services.messaging.message_handlers.JobResultRepository')
    @patch('app.services.messaging.message_handlers.JobStateMachine')
    @patch('app.services.messaging.message_handlers.RedisServiceFactory')
    @patch('app.services.messaging.message_handlers.ChunksRedisService')
    async def test_handle_result_success(
        self,
        mock_chunks_service,
        mock_redis_factory,
        mock_state_machine,
        mock_job_result_repo,
        mock_create_kb,
        mock_db_context
    ):
        """测试处理结果消息成功"""
        # 模拟数据库上下文
        mock_db = AsyncMock()
        mock_db_context.return_value.__aenter__.return_value = mock_db
        
        # 模拟知识库存储
        mock_create_kb.return_value = None
        
        # 模拟Redis服务
        mock_redis_service = MagicMock()
        mock_redis_factory.get_service.return_value = mock_redis_service
        
        # 模拟Chunks服务
        mock_chunks_svc = MagicMock()
        mock_chunks_service.return_value = mock_chunks_svc
        mock_chunks_svc.get_chunks = AsyncMock(return_value=[{"id": 1, "content": "test"}])
        mock_chunks_svc.delete_chunks = AsyncMock()
        
        # 模拟JobResult仓库
        mock_result_repo = MagicMock()
        mock_job_result_repo.return_value = mock_result_repo
        mock_job_result = MagicMock()
        mock_job_result.id = "result_123"
        mock_result_repo.upsert_job_result = AsyncMock(return_value=mock_job_result)
        mock_result_repo.replace_chunks = AsyncMock()
        
        # 模拟状态机
        mock_sm = MagicMock()
        mock_state_machine.return_value = mock_sm
        mock_sm.mark_completed = AsyncMock(return_value=True)
        
        # 创建消息
        message = JobResultMessage(
            job_id="test_job_123",
            chunks_job_id="test_job_123",
            result_s3_key="s3://bucket/key.zip",
            checksum="abc123",
            zip_size=1024,
            stored_count=10,
            kb_records=[{"content": "test", "path": "/test"}]
        )
        
        # 执行处理
        result = await _handle_result_async(message)
        
        # 验证结果
        assert result['status'] == 'success'
        assert result['stored_count'] == 10
        mock_create_kb.assert_called_once()
        mock_result_repo.upsert_job_result.assert_called_once()
        mock_sm.mark_completed.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.services.messaging.message_handlers.get_db_context')
    @patch('app.services.messaging.message_handlers.JobStateMachine')
    async def test_handle_failure_success(self, mock_state_machine, mock_db_context):
        """测试处理失败消息成功"""
        # 模拟数据库上下文
        mock_db = AsyncMock()
        mock_db_context.return_value.__aenter__.return_value = mock_db
        
        # 模拟状态机
        mock_sm = MagicMock()
        mock_state_machine.return_value = mock_sm
        mock_sm.mark_failed = AsyncMock(return_value=True)
        
        # 创建消息
        message = JobFailureMessage(
            job_id="test_job_123",
            error_message="Test error",
            error_type="ValueError"
        )
        
        # 执行处理
        result = await _handle_failure_async(message)
        
        # 验证结果
        assert result['status'] == 'success'
        assert result['error_message'] == "Test error"
        mock_sm.mark_failed.assert_called_once_with(
            mock_db, "test_job_123", "Test error"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

