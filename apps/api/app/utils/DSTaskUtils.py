import time
from typing import Union, List

from app.services.ai import ai_query_service
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
