"""
LLM API 通用工具函数
这些函数被多个服务使用，保留在 shared-python 中
"""
from typing import Any, Callable, Dict, List


async def use_llm_api(
    call_llm: Callable,
    histories: List,
    paras: Dict[str, Any],
    config: Dict[str, Any] = None
) -> tuple:
    """
    使用 LLM API 的通用封装
    
    Args:
        call_llm: LLM 调用函数
        histories: 历史对话记录
        paras: 参数字典
        config: 配置字典
    
    Returns:
        (结果, 历史记录) 元组
    """
    paras.update({'histories': histories})
    print(f"\n🚀 当前大模型任务 {paras['task']}...")
    result = call_llm(paras=paras, config=config)
    try:
        use_stream = paras['stream']
    except:
        use_stream = False

    if use_stream:  # 流式生成器，不追加 history，交给前端去消费
        return result, histories
    else:  # 非流式：追加 history 并返回答案
        if (paras.get('task') != 'if-history') and paras.get('use_his'):
            histories.append((paras['query'], result))
        return result, histories

