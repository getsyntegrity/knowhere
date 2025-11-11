"""
消息吞吐量性能测试
测试消息发布和消费的性能指标
"""
import pytest
import time
import asyncio
from kombu import Connection, Exchange, Queue, Consumer

from app.services.messaging import get_message_publisher
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
    
    queue = Queue(
        messaging_config.QUEUE_STATUS_UPDATES,
        exchange=exchange,
        routing_key=messaging_config.ROUTING_KEY_STATUS_UPDATE,
        durable=True
    )
    
    channel = rabbitmq_connection.default_channel
    exchange.declare(channel=channel)
    queue.declare(channel=channel)
    queue.bind(exchange).declare(channel=channel)
    
    return queue


class TestMessagePerformance:
    """消息性能测试类"""
    
    def test_publish_throughput(self, setup_rabbitmq):
        """测试消息发布吞吐量"""
        publisher = get_message_publisher()
        
        # 测试参数
        message_count = 100
        job_id_prefix = f"perf_test_{int(time.time())}"
        
        # 开始计时
        start_time = time.time()
        
        # 批量发布消息
        for i in range(message_count):
            publisher.publish_status_update(
                job_id=f"{job_id_prefix}_{i}",
                status="running",
                trigger="performance_test",
                async_mode=False
            )
        
        # 结束计时
        end_time = time.time()
        duration = end_time - start_time
        
        # 计算吞吐量
        throughput = message_count / duration
        
        print(f"\n发布性能测试结果:")
        print(f"  消息数量: {message_count}")
        print(f"  总耗时: {duration:.2f}秒")
        print(f"  吞吐量: {throughput:.2f} 消息/秒")
        print(f"  平均延迟: {(duration / message_count) * 1000:.2f} 毫秒/消息")
        
        # 断言：至少应该达到10消息/秒
        assert throughput >= 10, f"吞吐量过低: {throughput:.2f} 消息/秒"
    
    def test_consume_throughput(self, setup_rabbitmq, rabbitmq_connection):
        """测试消息消费吞吐量"""
        publisher = get_message_publisher()
        received_messages = []
        
        # 创建消费者
        queue = setup_rabbitmq
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
        
        # 发布测试消息
        message_count = 50
        job_id_prefix = f"consume_test_{int(time.time())}"
        
        publish_start = time.time()
        for i in range(message_count):
            publisher.publish_status_update(
                job_id=f"{job_id_prefix}_{i}",
                status="running",
                trigger="consume_test",
                async_mode=False
            )
        publish_end = time.time()
        
        # 消费消息（等待最多10秒）
        consume_start = time.time()
        timeout = 10
        start_time = time.time()
        while len(received_messages) < message_count and (time.time() - start_time) < timeout:
            try:
                rabbitmq_connection.drain_events(timeout=0.5)
            except Exception:
                pass
        consume_end = time.time()
        
        consumer.cancel()
        
        # 计算性能指标
        publish_duration = publish_end - publish_start
        consume_duration = consume_end - consume_start
        total_duration = consume_end - publish_start
        
        publish_throughput = message_count / publish_duration if publish_duration > 0 else 0
        consume_throughput = len(received_messages) / consume_duration if consume_duration > 0 else 0
        end_to_end_latency = total_duration / message_count if message_count > 0 else 0
        
        print(f"\n消费性能测试结果:")
        print(f"  发布消息数: {message_count}")
        print(f"  消费消息数: {len(received_messages)}")
        print(f"  发布耗时: {publish_duration:.2f}秒")
        print(f"  消费耗时: {consume_duration:.2f}秒")
        print(f"  总耗时: {total_duration:.2f}秒")
        print(f"  发布吞吐量: {publish_throughput:.2f} 消息/秒")
        print(f"  消费吞吐量: {consume_throughput:.2f} 消息/秒")
        print(f"  端到端延迟: {end_to_end_latency * 1000:.2f} 毫秒/消息")
        
        # 验证
        assert len(received_messages) >= message_count * 0.9, f"消费消息数不足: {len(received_messages)}/{message_count}"
        assert consume_throughput >= 5, f"消费吞吐量过低: {consume_throughput:.2f} 消息/秒"
    
    def test_concurrent_publish(self, setup_rabbitmq):
        """测试并发发布性能"""
        publisher = get_message_publisher()
        
        # 测试参数
        concurrent_count = 10
        messages_per_thread = 10
        total_messages = concurrent_count * messages_per_thread
        job_id_prefix = f"concurrent_test_{int(time.time())}"
        
        def publish_batch(thread_id):
            """批量发布消息"""
            for i in range(messages_per_thread):
                publisher.publish_status_update(
                    job_id=f"{job_id_prefix}_t{thread_id}_m{i}",
                    status="running",
                    trigger="concurrent_test",
                    async_mode=False
                )
        
        # 并发发布
        import threading
        threads = []
        start_time = time.time()
        
        for i in range(concurrent_count):
            thread = threading.Thread(target=publish_batch, args=(i,))
            threads.append(thread)
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        duration = end_time - start_time
        throughput = total_messages / duration
        
        print(f"\n并发发布性能测试结果:")
        print(f"  并发线程数: {concurrent_count}")
        print(f"  每线程消息数: {messages_per_thread}")
        print(f"  总消息数: {total_messages}")
        print(f"  总耗时: {duration:.2f}秒")
        print(f"  吞吐量: {throughput:.2f} 消息/秒")
        
        # 断言：并发情况下应该达到至少50消息/秒
        assert throughput >= 50, f"并发吞吐量过低: {throughput:.2f} 消息/秒"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

