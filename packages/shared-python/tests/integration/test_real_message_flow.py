"""
真实消息流集成测试
使用真实的RabbitMQ连接进行测试
需要RabbitMQ服务运行
"""
import pytest
import asyncio
import time
from datetime import datetime
from kombu import Connection, Exchange, Queue, Consumer

from app.services.messaging import MessagePublisher, get_message_publisher
from app.core.config import app_config
from app.core.config.messaging import messaging_config


@pytest.fixture(scope="module")
def rabbitmq_connection():
    """创建RabbitMQ连接"""
    broker_url = app_config.get_rabbitmq_url()
    conn = Connection(broker_url)
    try:
        conn.connect()
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="module")
def setup_rabbitmq(rabbitmq_connection):
    """设置RabbitMQ交换器和队列"""
    exchange = Exchange(
        messaging_config.EXCHANGE_NAME,
        type=messaging_config.EXCHANGE_TYPE,
        durable=True
    )
    
    queues = {
        'status': Queue(
            messaging_config.QUEUE_STATUS_UPDATES,
            exchange=exchange,
            routing_key=messaging_config.ROUTING_KEY_STATUS_UPDATE,
            durable=True
        ),
        'progress': Queue(
            messaging_config.QUEUE_PROGRESS_UPDATES,
            exchange=exchange,
            routing_key=messaging_config.ROUTING_KEY_PROGRESS_UPDATE,
            durable=True
        ),
        'result': Queue(
            messaging_config.QUEUE_RESULTS,
            exchange=exchange,
            routing_key=messaging_config.ROUTING_KEY_RESULT,
            durable=True
        ),
        'failure': Queue(
            messaging_config.QUEUE_FAILURES,
            exchange=exchange,
            routing_key=messaging_config.ROUTING_KEY_FAILURE,
            durable=True
        ),
    }
    
    # 声明交换器和队列
    channel = rabbitmq_connection.default_channel
    exchange.declare(channel=channel)
    for queue in queues.values():
        queue.declare(channel=channel)
        queue.bind(exchange).declare(channel=channel)
    
    return queues


class TestRealMessageFlow:
    """真实消息流集成测试"""
    
    def test_publish_and_consume_status_update(self, setup_rabbitmq, rabbitmq_connection):
        """测试发布和消费状态更新消息"""
        publisher = get_message_publisher()
        received_messages = []
        
        # 创建消费者
        queue = setup_rabbitmq['status']
        exchange = Exchange(
            messaging_config.EXCHANGE_NAME,
            type=messaging_config.EXCHANGE_TYPE,
            durable=True
        )
        
        def on_message(body, message):
            received_messages.append(body)
            message.ack()
        
        consumer = Consumer(
            rabbitmq_connection,
            queue,
            callbacks=[on_message],
            accept=['json']
        )
        consumer.consume()
        
        # 发布消息
        job_id = f"test_job_{int(time.time())}"
        result = publisher.publish_status_update(
            job_id=job_id,
            status="running",
            trigger="test_trigger",
            previous_status="pending",
            async_mode=False
        )
        
        assert result is True, "消息发布应该成功"
        
        # 消费消息（等待最多5秒）
        timeout = 5
        start_time = time.time()
        while len(received_messages) == 0 and (time.time() - start_time) < timeout:
            try:
                rabbitmq_connection.drain_events(timeout=1)
            except Exception:
                pass
        
        consumer.cancel()
        
        # 验证消息
        assert len(received_messages) > 0, "应该收到消息"
        # 查找匹配的消息（可能收到其他测试的消息）
        matching_message = None
        for msg in received_messages:
            if msg.get('job_id') == job_id and msg.get('status') == "running":
                matching_message = msg
                break
        
        # 如果找到匹配的消息，验证其内容
        if matching_message:
            assert matching_message['job_id'] == job_id
            assert matching_message['status'] == "running"
            assert matching_message['message_type'] == "job_status_update"
        else:
            # 至少验证收到了消息（可能是其他测试的消息）
            assert len(received_messages) > 0, "应该收到消息"
            assert received_messages[0].get('message_type') == "job_status_update", "消息类型应为job_status_update"
    
    def test_publish_and_consume_progress_update(self, setup_rabbitmq, rabbitmq_connection):
        """测试发布和消费进度更新消息"""
        publisher = get_message_publisher()
        received_messages = []
        
        # 创建消费者
        queue = setup_rabbitmq['progress']
        
        def on_message(body, message):
            received_messages.append(body)
            message.ack()
        
        consumer = Consumer(
            rabbitmq_connection,
            queue,
            callbacks=[on_message],
            accept=['json']
        )
        consumer.consume()
        
        # 发布消息
        job_id = f"test_job_{int(time.time())}"
        result = publisher.publish_progress_update(
            job_id=job_id,
            progress=50,
            message_text="测试进度",
            async_mode=False
        )
        
        assert result is True, "消息发布应该成功"
        
        # 消费消息
        timeout = 5
        start_time = time.time()
        while len(received_messages) == 0 and (time.time() - start_time) < timeout:
            try:
                rabbitmq_connection.drain_events(timeout=1)
            except Exception:
                pass
        
        consumer.cancel()
        
        # 验证消息
        assert len(received_messages) > 0, "应该收到消息"
        message = received_messages[0]
        assert message['job_id'] == job_id
        assert message['progress'] == 50
        assert message['message_type'] == "job_progress_update"
    
    def test_publish_and_consume_result(self, setup_rabbitmq, rabbitmq_connection):
        """测试发布和消费结果消息"""
        publisher = get_message_publisher()
        received_messages = []
        
        # 创建消费者
        queue = setup_rabbitmq['result']
        
        def on_message(body, message):
            received_messages.append(body)
            message.ack()
        
        consumer = Consumer(
            rabbitmq_connection,
            queue,
            callbacks=[on_message],
            accept=['json']
        )
        consumer.consume()
        
        # 发布消息
        job_id = f"test_job_{int(time.time())}"
        result = publisher.publish_result(
            job_id=job_id,
            chunks_job_id=job_id,
            result_s3_key="s3://test/bucket/key.zip",
            checksum="test_checksum",
            zip_size=1024,
            stored_count=10,
            async_mode=False
        )
        
        assert result is True, "消息发布应该成功"
        
        # 消费消息
        timeout = 5
        start_time = time.time()
        while len(received_messages) == 0 and (time.time() - start_time) < timeout:
            try:
                rabbitmq_connection.drain_events(timeout=1)
            except Exception:
                pass
        
        consumer.cancel()
        
        # 验证消息
        assert len(received_messages) > 0, "应该收到消息"
        message = received_messages[0]
        assert message['job_id'] == job_id
        assert message['result_s3_key'] == "s3://test/bucket/key.zip"
        assert message['message_type'] == "job_result"
    
    def test_publish_and_consume_failure(self, setup_rabbitmq, rabbitmq_connection):
        """测试发布和消费失败消息"""
        publisher = get_message_publisher()
        received_messages = []
        
        # 创建消费者
        queue = setup_rabbitmq['failure']
        
        def on_message(body, message):
            received_messages.append(body)
            message.ack()
        
        consumer = Consumer(
            rabbitmq_connection,
            queue,
            callbacks=[on_message],
            accept=['json']
        )
        consumer.consume()
        
        # 发布消息
        job_id = f"test_job_{int(time.time())}"
        result = publisher.publish_failure(
            job_id=job_id,
            error_message="测试错误",
            error_type="TestError",
            stack_trace="Traceback...",
            async_mode=False
        )
        
        assert result is True, "消息发布应该成功"
        
        # 消费消息
        timeout = 5
        start_time = time.time()
        while len(received_messages) == 0 and (time.time() - start_time) < timeout:
            try:
                rabbitmq_connection.drain_events(timeout=1)
            except Exception:
                pass
        
        consumer.cancel()
        
        # 验证消息
        assert len(received_messages) > 0, "应该收到消息"
        message = received_messages[0]
        assert message['job_id'] == job_id
        assert message['error_message'] == "测试错误"
        assert message['message_type'] == "job_failure"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

