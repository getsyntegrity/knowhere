import asyncio
import json
import random
import time
from app.core.dependencies import get_redis_service
from app.services.redis import RedisService
from app.services.redis.task_redis_service import TaskRedisService
from app.utils.DSTaskUtils import TaskFailedError, TaskTimeoutError
from app.utils.DeepSeekClient import DeepSeekRedisStreamClient


async def wait_for_job_result(job, timeout=None):
    from app.core.constants import APIConstants
    if timeout is None:
        timeout = APIConstants.TASK_TIMEOUT
    """等待ARQ任务完成并返回结果"""
    start_time = time.time()
    while True:
        # 检查超时
        if time.time() - start_time > timeout:
            raise TaskTimeoutError(f"任务在 {timeout} 秒内未完成")

        # 获取任务状态
        job_status = await job.status()

        if job_status == 'complete':
            # 获取任务结果
            result = await job.result()
            if isinstance(result, dict) and 'result' in result:
                return result['result']
            return result

        elif job_status == 'failed':
            raise TaskFailedError("任务执行失败")

        # 等待一段时间再检查
        await asyncio.sleep(2)

async def call_streaming_aif_api(prompt: str):
    print(f"开始流式调用外部API，prompt: {prompt}")
    words =f"这是关于“{prompt}”的回答。它由FastAPI和Arq驱动，展现了现代异步架构的强大能力..."
    for word in words:
        yield f"{word} "
        await asyncio.sleep(random.uniform(0.1, 0.3))
    print("API 内容流式传输完毕。")

async def process_ai_query(ctx: dict, prompt: str, temperature: float=0.1):
    #如果要通道                                        管理，对通道赋值
    job_id = ctx['job_id']
    job_try = ctx['job_try']
    
    # 使用新的Redis服务
    redis_service = await get_redis_service()
    task_service = TaskRedisService(redis_service)
    
    #将job_id作为观察项，避免任务失败后无法重启问题，同时保持同步的ds和异步的arq任务绑定
    conversation_id = job_id
    ai_client = DeepSeekRedisStreamClient()

    async def update_status(status_text: str):
        await task_service.set_task_status(job_id, status_text)
    
    async def stream_callback(chunk: str, chunk_size: int, total_size: int):
        if chunk:
            await task_service.push_stream_data(job_id, chunk)

    try:
        # 创建任务记录
        await task_service.create_task(job_id, {
            "prompt": prompt,
            "temperature": temperature,
            "job_try": job_try,
            "conversation_id": conversation_id
        })
        
        await update_status(f"任务已开始 (尝试次数: {job_try})")
        await update_status("正在连接AI大模型...")
        full_result = await ai_client.chat_completion(
            messages=prompt,
            temperature=temperature,
            conversation_id=conversation_id,
            stream_key=f"task:{job_id}:stream"  # 保持兼容性
        )
        await update_status("started！")
        await task_service.save_task_result(job_id, full_result)
        await update_status("complete")
        return {'status': '任务成功完成', 'result': safe_json_dumps(full_result)}
    except Exception as e:
        error_message = f"任务失败：{str(e)}"
        #任务失败，DS更新任务状态，接续
        await task_service.mark_task_failed(job_id, error_message)
        return {'status': '任务失败', 'error': str(e)}

def safe_json_dumps(obj):
    """
    安全的JSON序列化函数
    """
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(obj)