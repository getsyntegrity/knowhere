"""
Redis优化使用示例
"""
import asyncio
import json
from app.services.redis import RedisServiceFactory
from app.services.redis.task_redis_service import TaskRedisService
from app.services.redis.user_redis_service import UserRedisService
from app.services.redis.redis_monitor import RedisMonitor
from app.services.redis.redis_alerts import RedisAlertManager


async def redis_optimization_example():
    """Redis优化使用示例"""
    
    # 1. 获取Redis服务实例
    redis_service = RedisServiceFactory.get_service()
    
    print("=== Redis优化使用示例 ===")
    
    # 2. 基础操作示例
    print("\n1. 基础操作示例:")
    
    # 设置键值
    await redis_service.set("demo:key1", "Hello Redis!")
    await redis_service.set("demo:key2", {"name": "test", "value": 123})
    
    # 获取键值
    value1 = await redis_service.get("demo:key1")
    value2 = await redis_service.get("demo:key2")
    
    print(f"Key1: {value1}")
    print(f"Key2: {value2}")
    
    # 3. 任务服务示例
    print("\n2. 任务服务示例:")
    
    task_service = TaskRedisService(redis_service)
    
    # 创建任务
    task_id = "demo_task_001"
    task_data = {
        "user_id": "user_123",
        "task_type": "demo",
        "description": "演示任务"
    }
    
    success = await task_service.create_task(task_id, task_data)
    print(f"任务创建: {'成功' if success else '失败'}")
    
    # 更新任务状态
    await task_service.set_task_status(task_id, "processing")
    await task_service.update_task_progress(task_id, 50, "处理中...")
    
    # 保存任务结果
    result = {"status": "completed", "data": "任务完成"}
    await task_service.save_task_result(task_id, result)
    
    # 获取任务信息
    status = await task_service.get_task_status(task_id)
    progress = await task_service.get_task_progress(task_id)
    task_result = await task_service.get_task_result(task_id)
    
    print(f"任务状态: {status}")
    print(f"任务进度: {progress}")
    print(f"任务结果: {task_result}")
    
    # 4. 用户服务示例
    print("\n3. 用户服务示例:")
    
    user_service = UserRedisService(redis_service)
    username = "demo_user"
    
    # 保存用户配置
    user_config = {
        "theme": "dark",
        "language": "zh-CN",
        "notifications": True
    }
    await user_service.save_user_config(username, user_config)
    
    # 更新用户会话
    session_data = {
        "login_time": "2025-01-08 10:00:00",
        "ip_address": "192.168.1.100"
    }
    await user_service.update_user_session(username, session_data)
    
    # 更新用户活动
    await user_service.update_user_activity(username, "active")
    
    # 获取用户信息
    config = await user_service.get_user_config(username)
    session = await user_service.get_user_session(username)
    activity = await user_service.get_user_activity(username)
    
    print(f"用户配置: {config}")
    print(f"用户会话: {session}")
    print(f"用户活动: {activity}")
    
    # 5. 监控示例
    print("\n4. 监控示例:")
    
    monitor = RedisMonitor(redis_service)
    
    # 检查健康状态
    health = await monitor.check_health()
    print(f"Redis健康状态: {health['is_healthy']}")
    print(f"PING延迟: {health['ping_latency']}ms")
    print(f"内存使用率: {health['memory_usage']}%")
    
    # 获取内存使用情况
    memory = await monitor.get_memory_usage()
    print(f"内存使用: {memory['used_memory_human']}")
    print(f"内存峰值: {memory['used_memory_peak_human']}")
    
    # 获取业务指标
    business_metrics = await monitor.get_business_metrics()
    print(f"在线用户数: {business_metrics.get('online_users_count', 0)}")
    print(f"处理中任务数: {business_metrics.get('processing_tasks_count', 0)}")
    
    # 6. 告警示例
    print("\n5. 告警示例:")
    
    alert_manager = RedisAlertManager(monitor)
    
    # 检查告警
    alerts = await alert_manager.check_alerts()
    print(f"当前告警数量: {len(alerts)}")
    
    # 获取告警统计
    stats = alert_manager.get_alert_stats()
    print(f"告警统计: {stats}")
    
    # 7. 键值命名规范示例
    print("\n6. 键值命名规范示例:")
    
    from app.utils.redis_key_builder import redis_key_builder
    
    # 展示不同类型的键
    keys = {
        "用户配置": redis_key_builder.user_config("test_user"),
        "任务状态": redis_key_builder.task_status("task_123"),
        "对话状态": redis_key_builder.conversation_state("conv_123"),
        "知识库状态": redis_key_builder.kb_status("user_123"),
        "在线用户": redis_key_builder.set_online_users(),
        "错误日志": redis_key_builder.list_error_logs()
    }
    
    for key_type, key_name in keys.items():
        print(f"{key_type}: {key_name}")
    
    # 8. 清理示例数据
    print("\n7. 清理示例数据:")
    
    # 清理任务数据
    await task_service.cleanup_task(task_id)
    print("任务数据已清理")
    
    # 清理用户数据
    await user_service.cleanup_user_data(username)
    print("用户数据已清理")
    
    # 清理演示键
    await redis_service.delete("demo:key1", "demo:key2")
    print("演示键已清理")
    
    print("\n=== Redis优化示例完成 ===")


if __name__ == "__main__":
    asyncio.run(redis_optimization_example())
