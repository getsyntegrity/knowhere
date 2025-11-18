"""
AI服务模块（API专用）
所有AI服务现在都在共享包中，这里仅用于向后兼容
"""
from shared.services.ai import (AIQueryService, ai_query_service,
                                ai_query_service_arq, build_prompt,
                                eval_response, process_llm_history)

__all__ = [
    'build_prompt',
    'process_llm_history',
    'eval_response',
    'AIQueryService',
    'ai_query_service',
    'ai_query_service_arq'
]
