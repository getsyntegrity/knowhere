"""
Celery任务定义
迁移自ARQ任务，支持优先级和队列路由
"""
import asyncio
import json
import time
from typing import Dict, Any, List, Optional
from celery import Task
from loguru import logger

from app.core.celery_app import get_celery_app, get_task_priority, get_queue_name
from app.core.celery_router import CeleryTaskRouter, TaskContext, TaskType, UserLevel, DocumentImportance
from app.core.state_machine import JobStateMachine, JobState
from app.services.redis import RedisServiceFactory, TaskRedisService, UserRedisService

# 获取Celery应用
celery_app = get_celery_app()

# 创建路由器实例
task_router = CeleryTaskRouter()

class BaseTask(Task):
    """基础任务类，提供通用功能"""
    
    def on_success(self, retval, task_id, args, kwargs):
        """任务成功回调"""
        logger.info(f"任务 {task_id} 执行成功")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败回调"""
        logger.error(f"任务 {task_id} 执行失败: {exc}")
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """任务重试回调"""
        logger.warning(f"任务 {task_id} 重试: {exc}")

@celery_app.task(bind=True, base=BaseTask, name='app.tasks.celery_tasks.process_ai_query')
def process_ai_query(self, prompt: str, user_id: str, temperature: float = 0.1, 
                    conversation_id: str = None, **kwargs):
    """
    AI查询任务 - 高优先级
    """
    try:
        # 创建任务上下文
        context = task_router.create_task_context(
            task_type='ai_query',
            user_id=user_id,
            user_level=kwargs.get('user_level', 'standard'),
            is_urgent=kwargs.get('is_urgent', False),
            metadata=kwargs
        )
        
        # 更新任务状态
        self.update_state(state='PROGRESS', meta={'status': '正在连接AI大模型...'})
        
        # 异步执行AI查询
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(_process_ai_query_async(
                prompt, user_id, temperature, conversation_id, context
            ))
            return result
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"AI查询任务失败: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)

async def _process_ai_query_async(prompt: str, user_id: str, temperature: float,
                                 conversation_id: str, context: TaskContext):
    """异步AI查询处理"""
    # 获取Redis服务
    redis_service = RedisServiceFactory.get_service()
    task_service = TaskRedisService(redis_service)
    
    # 初始化状态机
    state_machine = JobStateMachine(redis_service)
    
    # 设置任务状态
    await task_service.set_task_status(context.user_id, "正在连接AI大模型...")
    
    # 延迟导入DeepSeek客户端
    from app.utils.DeepSeekClient import DeepSeekRedisStreamClient
    ai_client = DeepSeekRedisStreamClient(redis_service)
    
    # 设置对话ID
    if not conversation_id:
        conversation_id = f"ai_query_{user_id}_{int(time.time())}"
    
    # 执行AI查询
    try:
        logger.debug(f'process_ai_query_async prompt: {prompt}')
        logger.debug(f'process_ai_query_async temperature: {temperature}')
        logger.debug(f'process_ai_query_async conversation_id: {conversation_id}')
        
        # 更新状态为处理中
        await state_machine.set_task_timeout(context.user_id, JobState.PROCESSING.value)
        
        result = await ai_client.chat_completion(
            messages=prompt,
            temperature=temperature,
            conversation_id=conversation_id,
        )
        logger.debug(f'process_ai_query_async result: {result}')
        
        # 保存结果
        await task_service.save_task_result(context.user_id, {
            'result': result,
            'conversation_id': conversation_id,
            'timestamp': time.time()
        })
        
        await task_service.set_task_status(context.user_id, "complete")
        return {'status': 'success', 'result': result}
        
    except Exception as e:
        await task_service.mark_task_failed(context.user_id, str(e))
        raise

@celery_app.task(bind=True, base=BaseTask, name='app.tasks.celery_tasks.process_document')
def process_document(self, file_path: str, user_id: str, doc_type: str, **kwargs):
    """
    文档处理任务 - 中优先级
    """
    try:
        # 创建任务上下文
        context = task_router.create_task_context(
            task_type='document_processing',
            user_id=user_id,
            document_importance=kwargs.get('document_importance', 'medium'),
            is_urgent=kwargs.get('is_urgent', False),
            metadata=kwargs
        )
        
        # 更新任务状态
        self.update_state(state='PROGRESS', meta={'status': '开始处理文档...'})
        
        # 异步执行文档处理
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(_process_document_async(
                file_path, user_id, doc_type, context
            ))
            return result
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"文档处理任务失败: {e}")
        raise self.retry(exc=e, countdown=120, max_retries=2)

async def _process_document_async(file_path: str, user_id: str, doc_type: str, context: TaskContext):
    """异步文档处理"""
    # 获取Redis服务
    redis_service = RedisServiceFactory.get_service()
    task_service = TaskRedisService(redis_service)
    user_service = UserRedisService(redis_service)
    
    # 设置任务状态
    await task_service.set_task_status(context.user_id, "开始处理文档...")
    
    try:
        # 获取用户配置
        user_config = await user_service.get_user_config(context.user_id)
        if not user_config:
            raise ValueError("用户配置不存在")
        
        # 延迟导入文档处理服务
        from app.services.knowledge.knowledge_base_service import checkerboard_inject_parse
        
        # 调用文档处理服务
        result = await checkerboard_inject_parse(
            file_full_path=file_path,
            filename=file_path.split('/')[-1],
            kb_dir=kwargs.get('kb_dir', '默认目录'),
            doc_type=doc_type,
            smart_title_parse=kwargs.get('smart_title_parse', True),
            summary_image=kwargs.get('summary_image', True),
            summary_table=kwargs.get('summary_table', True),
            summary_txt=kwargs.get('summary_txt', True),
            add_frag_desc=kwargs.get('add_frag_desc', True)
        )
        
        # 保存结果
        await task_service.save_task_result(context.user_id, {
            'file_path': file_path,
            'doc_type': doc_type,
            'result': result,
            'timestamp': time.time()
        })
        
        await task_service.set_task_status(context.user_id, "complete")
        return {'status': 'success', 'result': result}
        
    except Exception as e:
        await task_service.mark_task_failed(context.user_id, str(e))
        raise

@celery_app.task(bind=True, base=BaseTask, name='app.tasks.celery_tasks.encode_knowledge_base')
def encode_knowledge_base(self, user_id: str, kb_path: str, mode: str = "add", **kwargs):
    """
    知识库编码任务 - 中优先级
    """
    try:
        # 创建任务上下文
        context = task_router.create_task_context(
            task_type='kb_encoding',
            user_id=user_id,
            document_importance=kwargs.get('document_importance', 'medium'),
            metadata=kwargs
        )
        
        # 更新任务状态
        self.update_state(state='PROGRESS', meta={'status': '开始编码知识库...'})
        
        # 异步执行知识库编码
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(_encode_knowledge_base_async(
                user_id, kb_path, mode, context
            ))
            return result
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"知识库编码任务失败: {e}")
        raise self.retry(exc=e, countdown=180, max_retries=2)

async def _encode_knowledge_base_async(user_id: str, kb_path: str, mode: str, context: TaskContext):
    """异步知识库编码"""
    # 获取Redis服务
    redis_service = RedisServiceFactory.get_service()
    task_service = TaskRedisService(redis_service)
    user_service = UserRedisService(redis_service)
    
    # 设置任务状态
    await task_service.set_task_status(context.user_id, "开始编码知识库...")
    
    try:
        # 获取用户配置
        user_config = await user_service.get_user_config(context.user_id)
        if not user_config:
            raise ValueError("用户配置不存在")
        
        # 延迟导入知识库编码服务
        from app.services.knowledge.kb_encoder_service import encode_kb
        
        # 调用知识库编码服务
        result = await encode_kb(
            user_config, 
            add_dir=kb_path, 
            mode=mode
        )
        
        # 保存结果
        await task_service.save_task_result(context.user_id, {
            'kb_path': kb_path,
            'mode': mode,
            'result': result,
            'timestamp': time.time()
        })
        
        await task_service.set_task_status(context.user_id, "complete")
        return {'status': 'success', 'result': result}
        
    except Exception as e:
        await task_service.mark_task_failed(context.user_id, str(e))
        raise

@celery_app.task(bind=True, base=BaseTask, name='app.tasks.celery_tasks.batch_file_processing')
def batch_file_processing(self, file_paths: List[str], user_id: str, **kwargs):
    """
    批量文件处理任务 - 中优先级
    """
    try:
        # 创建任务上下文
        context = task_router.create_task_context(
            task_type='batch_processing',
            user_id=user_id,
            metadata=kwargs
        )
        
        # 更新任务状态
        self.update_state(state='PROGRESS', meta={'status': f'开始处理 {len(file_paths)} 个文件...'})
        
        results = []
        for i, file_path in enumerate(file_paths):
            try:
                # 更新进度
                self.update_state(
                    state='PROGRESS', 
                    meta={'status': f'处理文件 {i+1}/{len(file_paths)}: {file_path}'}
                )
                
                # 处理单个文件
                result = process_document.delay(file_path, user_id, kwargs.get('doc_type', 'auto'))
                results.append({'file_path': file_path, 'task_id': result.id})
                
            except Exception as e:
                logger.error(f"处理文件 {file_path} 失败: {e}")
                results.append({'file_path': file_path, 'error': str(e)})
        
        return {'status': 'success', 'results': results}
        
    except Exception as e:
        logger.error(f"批量文件处理任务失败: {e}")
        raise self.retry(exc=e, countdown=300, max_retries=1)

@celery_app.task(bind=True, base=BaseTask, name='app.tasks.celery_tasks.user_analytics')
def user_analytics(self, user_id: str, analytics_type: str, **kwargs):
    """
    用户分析任务 - 低优先级
    """
    try:
        # 创建任务上下文
        context = task_router.create_task_context(
            task_type='analytics',
            user_id=user_id,
            metadata=kwargs
        )
        
        # 更新任务状态
        self.update_state(state='PROGRESS', meta={'status': f'开始分析用户数据: {analytics_type}'})
        
        # 模拟分析处理
        time.sleep(10)  # 模拟处理时间
        
        result = {
            'user_id': user_id,
            'analytics_type': analytics_type,
            'timestamp': time.time(),
            'data': {'sample': 'analysis_result'}
        }
        
        return {'status': 'success', 'result': result}
        
    except Exception as e:
        logger.error(f"用户分析任务失败: {e}")
        raise self.retry(exc=e, countdown=600, max_retries=1)

@celery_app.task(bind=True, base=BaseTask, name='app.tasks.celery_tasks.data_backup')
def data_backup(self, backup_type: str, **kwargs):
    """
    数据备份任务 - 低优先级
    """
    try:
        # 创建任务上下文
        context = task_router.create_task_context(
            task_type='backup',
            user_id='system',
            metadata=kwargs
        )
        
        # 更新任务状态
        self.update_state(state='PROGRESS', meta={'status': f'开始备份数据: {backup_type}'})
        
        # 模拟备份处理
        time.sleep(30)  # 模拟处理时间
        
        result = {
            'backup_type': backup_type,
            'timestamp': time.time(),
            'status': 'completed'
        }
        
        return {'status': 'success', 'result': result}
        
    except Exception as e:
        logger.error(f"数据备份任务失败: {e}")
        raise self.retry(exc=e, countdown=1800, max_retries=1)

@celery_app.task(bind=True, base=BaseTask, name='app.tasks.celery_tasks.log_processing')
def log_processing(self, log_type: str, **kwargs):
    """
    日志处理任务 - 低优先级
    """
    try:
        # 创建任务上下文
        context = task_router.create_task_context(
            task_type='log_processing',
            user_id='system',
            metadata=kwargs
        )
        
        # 更新任务状态
        self.update_state(state='PROGRESS', meta={'status': f'开始处理日志: {log_type}'})
        
        # 模拟日志处理
        time.sleep(20)  # 模拟处理时间
        
        result = {
            'log_type': log_type,
            'timestamp': time.time(),
            'status': 'processed'
        }
        
        return {'status': 'success', 'result': result}
        
    except Exception as e:
        logger.error(f"日志处理任务失败: {e}")
        raise self.retry(exc=e, countdown=900, max_retries=1)

@celery_app.task(bind=True, base=BaseTask, name='app.tasks.celery_tasks.cleanup_expired_tasks')
def cleanup_expired_tasks(self):
    """
    清理过期任务 - 定时任务
    """
    try:
        # 更新任务状态
        self.update_state(state='PROGRESS', meta={'status': '开始清理过期任务...'})
        
        # 异步执行清理
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(_cleanup_expired_tasks_async())
            return result
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"清理过期任务失败: {e}")
        raise

async def _cleanup_expired_tasks_async():
    """异步清理过期任务"""
    # 获取Redis服务
    redis_service = RedisServiceFactory.get_service()
    task_service = TaskRedisService(redis_service)
    
    # 这里可以实现具体的清理逻辑
    # 例如：删除超过24小时的任务数据
    
    return {'status': 'success', 'cleaned_count': 0}

@celery_app.task(bind=True, base=BaseTask, name='app.tasks.celery_tasks.backup_user_data')
def backup_user_data(self):
    """
    备份用户数据 - 定时任务
    """
    try:
        # 更新任务状态
        self.update_state(state='PROGRESS', meta={'status': '开始备份用户数据...'})
        
        # 模拟备份处理
        time.sleep(60)  # 模拟处理时间
        
        return {'status': 'success', 'backup_time': time.time()}
        
    except Exception as e:
        logger.error(f"备份用户数据失败: {e}")
        raise

@celery_app.task(bind=True, base=BaseTask, name='app.tasks.celery_tasks.process_user_analytics')
def process_user_analytics(self):
    """
    处理用户分析 - 定时任务
    """
    try:
        # 更新任务状态
        self.update_state(state='PROGRESS', meta={'status': '开始处理用户分析...'})
        
        # 模拟分析处理
        time.sleep(120)  # 模拟处理时间
        
        return {'status': 'success', 'analysis_time': time.time()}
        
    except Exception as e:
        logger.error(f"处理用户分析失败: {e}")
        raise
