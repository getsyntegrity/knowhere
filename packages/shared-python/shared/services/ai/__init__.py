"""
AI服务模块（共享）
包含prompt构建、响应处理和AI查询服务等通用功能
"""
from .prompt_service import build_prompt
from .response_process_service import eval_response, process_llm_history


__all__ = [
    'build_prompt',
    'process_llm_history',
    'eval_response',
]
