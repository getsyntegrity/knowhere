import asyncio
import time
from typing import Optional, Union, List
# ARQ依赖已移除，使用Celery替代

from app.core.config import redis_pool_manager
from app.services.ai import ai_query_service
from app.core.dependencies import get_redis_service
from app.services.redis import RedisService
from loguru import logger


class TaskTimeoutError(Exception):
    """任务超时异常"""
    pass


class TaskFailedError(Exception):
    """任务失败异常"""
    pass


async def prompt_task_result(prompt: Union[str, List[dict]], timeout: int = None, user_id: str = "system") -> str:
    from app.core.constants import APIConstants
    if timeout is None:
        timeout = APIConstants.PROMPT_TIMEOUT
    """
    根据prompt生成任务结果，这是一个阻塞式函数
    如果任务在指定时间内没有返回结果，则抛出超时异常
    :param prompt: 提示词，可以是字符串或消息列表
    :param timeout: 超时时间（秒），默认20秒
    :param user_id: 用户ID，默认为"system"
    :return: 任务结果字符串
    :raises TaskTimeoutError: 任务超时
    :raises TaskFailedError: 任务失败
    """
    try:
        # 使用统一的AI查询服务
        logger.info(f"提交AI查询任务, 超时时间: {timeout}秒")
        
        result = await ai_query_service.query_ai(
            messages=prompt,
            user_id=user_id,
            timeout=timeout
        )
        
        logger.info(f"AI查询任务完成")
        return result

    except (TaskTimeoutError, TaskFailedError):
        # 重新抛出自定义异常
        raise
    except Exception as e:
        logger.error(f"执行任务时发生未知错误: {str(e)}")
        raise TaskFailedError(f"执行任务时发生错误: {str(e)}")


async def _get_task_result(task_id: str) -> Optional[str]:
    """
    获取任务的最终结果
    :param task_id: 任务ID
    :return: 任务结果或None
    """
    try:
        redis_service = await get_redis_service()
        result_key = f"task:{task_id}:result"
        result = await redis_service.get(result_key)
        return result
    except Exception as e:
        logger.error(f"获取任务结果失败: {task_id}, 错误: {str(e)}")
        return None


async def _get_stream_content(task_id: str) -> List[str]:
    """
    获取任务的流式内容

    :param task_id: 任务ID
    :return: 内容块列表
    """
    try:
        redis_service = await get_redis_service()
        stream_key = f"task:{task_id}:stream"
        content_chunks = await redis_service.lrange(stream_key, 0, -1)
        return content_chunks if content_chunks else []
    except Exception as e:
        logger.error(f"获取流式内容失败: {task_id}, 错误: {str(e)}")
        return []


async def prompt_task_result_with_status(prompt: Union[str, List[dict]], timeout: int = None,
                                         user_id: str = "system") -> dict:
    from app.core.constants import APIConstants
    if timeout is None:
        timeout = APIConstants.PROMPT_STATUS_TIMEOUT
    """
    根据prompt生成任务结果，并返回详细状态信息

    :param prompt: 提示词，可以是字符串或消息列表
    :param timeout: 超时时间（秒），默认20秒
    :param user_id: 用户ID，默认为"system"
    :return: 包含结果和状态信息的字典
    """
    start_time = time.time()

    try:
        result = await prompt_task_result(prompt, timeout, user_id)
        elapsed_time = time.time() - start_time

        return {
            "success": True,
            "result": result,
            "elapsed_time": elapsed_time,
            "error": None
        }
    except (TaskTimeoutError, TaskFailedError) as e:
        elapsed_time = time.time() - start_time

        return {
            "success": False,
            "result": None,
            "elapsed_time": elapsed_time,
            "error": str(e)
        }


async def submit_task(prompt: Union[str, List[dict]], user_id: str = "system") -> str:
    """
    提交任务但不等待结果，立即返回任务ID
    :param prompt: 提示词，可以是字符串或消息列表
    :param user_id: 用户ID，默认为"system"
    :return: 任务ID
    """
    try:
        # 使用统一的AI查询服务（流式模式）
        logger.info(f"提交AI查询任务")
        
        result = await ai_query_service.query_ai_stream(
            messages=prompt,
            user_id=user_id
        )
        
        task_id = result.get('task_id', f"ai_query_{user_id}_{int(time.time())}")
        logger.info(f"任务已提交: {task_id}")
        return task_id
    except Exception as e:
        logger.error(f"提交任务时发生错误: {str(e)}")
        raise TaskFailedError(f"提交任务时发生错误: {str(e)}")


async def check_task_status(task_id: str) -> dict:
    """
    检查任务状态但不等待完成

    :param task_id: 任务ID
    :return: 包含任务状态信息的字典
    """
    try:
        redis_pool = await redis_pool_manager.get_pool()
        job = Job(task_id, redis=redis_pool)
        job_status = await job.status()

        if job_status == 'complete':
            # 获取任务结果
            result = await _get_task_result(task_id)
            if result:
                return {"status": "complete", "result": result}
            else:
                # 如果没有结果，尝试获取流式内容
                stream_content = await _get_stream_content(task_id)
                if stream_content:
                    return {"status": "complete", "result": ''.join(stream_content)}
                else:
                    return {"status": "complete", "result": ""}
        else:
            return {"status": job_status}
    except Exception as e:
        logger.error(f"检查任务状态时发生错误: {str(e)}")
        return {"status": "error", "error": str(e)}


async def batch_submit_tasks(prompts: List[Union[str, List[dict]]], user_ids: Union[str, List[str]] = "system") -> List[
    str]:
    """
    批量提交任务

    :param prompts: 提示词列表
    :param user_ids: 用户ID或用户ID列表，默认为"system"
    :return: 任务ID列表
    """
    if isinstance(user_ids, str):
        user_ids = [user_ids] * len(prompts)

    task_ids = []
    for prompt, user_id in zip(prompts, user_ids):
        try:
            task_id = await submit_task(prompt, user_id)
            task_ids.append(task_id)
        except Exception as e:
            logger.error(f"批量提交任务时发生错误: {str(e)}")
            task_ids.append(None)

    return task_ids


async def wait_for_tasks(task_ids: List[str], timeout: int = None, poll_interval: float = 0.5) -> List[dict]:
    from app.core.constants import APIConstants
    if timeout is None:
        timeout = APIConstants.TASK_WAIT_TIMEOUT
    """
    等待多个任务完成，支持并行处理

    :param task_ids: 任务ID列表
    :param timeout: 总超时时间（秒）
    :param poll_interval: 轮询间隔（秒）
    :return: 任务结果列表
    """
    start_time = time.time()
    results = [None] * len(task_ids)
    pending_indices = list(range(len(task_ids)))

    while pending_indices and time.time() - start_time < timeout:
        # 创建检查任务状态的协程列表
        check_tasks = [check_task_status(task_ids[i]) for i in pending_indices]

        # 并行检查所有待处理任务的状态
        statuses = await asyncio.gather(*check_tasks)

        # 处理已完成的任务
        still_pending = []
        for idx, status_dict in zip(pending_indices, statuses):
            if status_dict["status"] == "complete":
                results[idx] = status_dict.get("result", "")
            elif status_dict["status"] in ["failed", "not_found", "cancelled", "error"]:
                results[idx] = f"任务失败: {status_dict.get('error', status_dict['status'])}"
            else:
                still_pending.append(idx)

        # 更新待处理索引
        pending_indices = still_pending

        # 如果还有待处理任务，等待一段时间后再次检查
        if pending_indices:
            await asyncio.sleep(poll_interval)

    # 处理超时的任务
    for idx in pending_indices:
        results[idx] = f"任务超时: {task_ids[idx]}"

    return results