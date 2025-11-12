"""
AI查询服务
统一处理AI查询任务，支持Celery和ARQ两种模式
"""

import asyncio
import time
from typing import Any, Optional

from celery import current_task
from loguru import logger


class AIQueryService:
    """AI查询服务"""

    def __init__(self, use_celery: bool = True):
        """
        初始化AI查询服务

        Args:
            use_celery: 是否使用Celery，False则使用ARQ
        """
        self.use_celery = use_celery

    async def query_ai(
        self,
        messages: Any,
        user_id: str = "system",
        temperature: float = 0.1,
        conversation_id: Optional[str] = None,
        timeout: int = 90,
        **kwargs,
    ) -> Any:
        """
        执行AI查询

        Args:
            messages: 查询消息
            user_id: 用户ID
            temperature: 温度参数
            conversation_id: 对话ID
            timeout: 超时时间
            **kwargs: 其他参数

        Returns:
            AI查询结果
        """
        logger.info(
            f"📡 开始AI查询: user_id={user_id}, temperature={temperature}, timeout={timeout}s"
        )
        logger.debug(f"使用模式: {'Celery' if self.use_celery else 'ARQ'}")

        if self.use_celery:
            return await self._query_with_celery(
                messages, user_id, temperature, conversation_id, timeout, **kwargs
            )
        else:
            return await self._query_with_arq(
                messages, user_id, temperature, conversation_id, timeout, **kwargs
            )

    async def _query_with_celery(
        self,
        messages: Any,
        user_id: str,
        temperature: float,
        conversation_id: Optional[str],
        timeout: int,
        **kwargs,
    ) -> Any:
        """使用Celery执行AI查询"""
        try:
            logger.debug("检查是否在Celery worker内运行...")
            if self._running_inside_celery_worker():
                logger.info("✅ 在Celery worker内，使用内联执行模式")
                return await self._execute_inline(
                    messages=messages,
                    user_id=user_id,
                    temperature=temperature,
                    conversation_id=conversation_id,
                    **kwargs,
                )

            # 延迟导入避免循环导入
            logger.debug("不在Celery worker内，准备提交Celery任务...")
            from app.core.tasks.celery_tasks import (
                process_ai_query as celery_process_ai_query,
            )
            from app.core.celery_app import celery_app

            # 调试信息：显示Celery配置
            logger.info(f"📋 Celery配置信息:")
            logger.info(f"   Broker: {celery_app.conf.broker_url}")
            logger.info(f"   Backend: {celery_app.conf.result_backend}")
            logger.info(f"   任务名称: {celery_process_ai_query.name}")
            logger.info(
                f"   目标队列: {celery_app.conf.task_routes.get(celery_process_ai_query.name, {}).get('queue', 'default')}"
            )

            # 提交Celery任务
            logger.info(f"⏳ 正在提交Celery任务...")
            task = celery_process_ai_query.delay(
                prompt=messages,
                user_id=user_id,
                temperature=temperature,
                conversation_id=conversation_id,
                **kwargs,
            )
            logger.info(
                f"✅ Celery任务已提交，task_id={task.id}，等待结果（超时:{timeout}秒）..."
            )
            logger.info(f"   任务状态: {task.state}")

            # 等待任务完成（避免阻塞事件循环）
            logger.debug("开始等待Celery任务结果...")
            result = await asyncio.to_thread(task.get, timeout=timeout)
            logger.info("✅ Celery任务执行完成，收到结果")

            if result.get("status") == "success":
                logger.debug("任务执行成功，返回结果")
                return result.get("result", {})
            logger.error(f"❌ Celery任务失败: {result.get('error', '未知错误')}")
            raise Exception(f"Celery任务失败: {result.get('error', '未知错误')}")

        except Exception as e:
            logger.error(f"Celery AI查询失败: {e}")
            raise

    async def _query_with_arq(
        self,
        messages: Any,
        user_id: str,
        temperature: float,
        conversation_id: Optional[str],
        timeout: int,
        **kwargs,
    ) -> Any:
        """使用ARQ执行AI查询（向后兼容）"""
        try:
            # 提交ARQ任务（已弃用，仅用于向后兼容）
            raise NotImplementedError("ARQ模式已弃用，请使用Celery模式")

        except Exception as e:
            logger.error(f"ARQ AI查询失败: {e}")
            raise

    @staticmethod
    def _running_inside_celery_worker() -> bool:
        """检测当前是否处于Celery worker上下文"""
        try:
            return bool(current_task and getattr(current_task, "request", None))
        except Exception:
            return False

    async def _execute_inline(
        self,
        messages: Any,
        user_id: str,
        temperature: float,
        conversation_id: Optional[str],
        **kwargs,
    ) -> Any:
        """在当前Celery任务内直接执行AI查询，避免嵌套子任务阻塞"""
        logger.debug("开始内联执行AI查询...")
        from app.services.redis import RedisServiceFactory, TaskRedisService
        from app.utils.DeepSeekClient import DeepSeekRedisStreamClient

        logger.debug("获取Redis服务实例...")
        redis_service = RedisServiceFactory.get_service()
        task_service = TaskRedisService(redis_service)

        conversation = conversation_id or f"ai_query_{user_id}_{int(time.time())}"
        logger.debug(f"会话ID: {conversation}")

        logger.info("⏳ 正在连接AI大模型...")
        await task_service.set_task_status(user_id, "正在连接AI大模型...")

        logger.debug("初始化DeepSeek客户端...")
        ai_client = DeepSeekRedisStreamClient(redis_service)
        try:
            logger.info(f"🤖 开始调用DeepSeek API (temperature={temperature})...")
            start_time = time.time()
            result = await ai_client.chat_completion(
                messages=messages,
                temperature=temperature,
                conversation_id=conversation,
            )
            elapsed = time.time() - start_time
            logger.info(f"✅ DeepSeek API调用完成，耗时: {elapsed:.2f}秒")

            logger.debug("保存任务结果到Redis...")
            await task_service.save_task_result(
                user_id,
                {
                    "result": result,
                    "conversation_id": conversation,
                    "timestamp": time.time(),
                },
            )
            logger.debug("任务结果已保存")
            return result
        except Exception as exc:  # pragma: no cover - redis failure cases
            logger.error(f"❌ AI查询失败: {exc}")
            await task_service.mark_task_failed(user_id, str(exc))
            raise


# 全局AI查询服务实例
# 默认使用Celery，可以通过环境变量配置
ai_query_service = AIQueryService(use_celery=True)

# 向后兼容的ARQ服务实例
ai_query_service_arq = AIQueryService(use_celery=False)
