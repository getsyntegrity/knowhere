#!/usr/bin/env python3
"""
设置RabbitMQ交换器和队列
用于测试和开发环境
"""
import sys
from kombu import Connection, Exchange, Queue

# RabbitMQ连接配置
# 从环境变量或使用默认值
import os
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'admin')
RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASSWORD', 'admin123')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = os.getenv('RABBITMQ_PORT', '5672')
RABBITMQ_VHOST = os.getenv('RABBITMQ_VHOST', '/')

RABBITMQ_URL = f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}:{RABBITMQ_PORT}{RABBITMQ_VHOST}"

# 交换器和队列配置
EXCHANGE_NAME = "job_events"
EXCHANGE_TYPE = "direct"

QUEUES = {
    "job_progress_updates": {
        "name": "job_progress_updates",
        "routing_key": "job.progress.update"
    },
    "job_results": {
        "name": "job_results",
        "routing_key": "job.result"
    },
    "job_failures": {
        "name": "job_failures",
        "routing_key": "job.failure"
    }
}


def setup_rabbitmq():
    """设置RabbitMQ交换器和队列"""
    print("开始设置RabbitMQ...")
    
    try:
        with Connection(RABBITMQ_URL) as conn:
            # 创建交换器
            exchange = Exchange(EXCHANGE_NAME, type=EXCHANGE_TYPE, durable=True)
            exchange.declare(channel=conn.default_channel)
            print(f"✅ 交换器 '{EXCHANGE_NAME}' 创建成功")
            
            # 创建队列并绑定
            for queue_info in QUEUES.values():
                queue = Queue(
                    queue_info["name"],
                    exchange=exchange,
                    routing_key=queue_info["routing_key"],
                    durable=True,
                    auto_delete=False,
                    exclusive=False
                )
                queue.declare(channel=conn.default_channel)
                queue.bind(exchange).declare(channel=conn.default_channel)
                print(f"✅ 队列 '{queue_info['name']}' 创建并绑定成功 (routing_key: {queue_info['routing_key']})")
            
            print("\n✅ RabbitMQ设置完成！")
            return True
            
    except Exception as e:
        print(f"❌ RabbitMQ设置失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = setup_rabbitmq()
    sys.exit(0 if success else 1)

