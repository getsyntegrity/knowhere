"""
设备检查通用工具函数
这些函数被多个服务使用，保留在 shared-python 中
"""
from typing import Any, Dict

import requests
from loguru import logger


def check_internet(url: str = 'http://www.baidu.com') -> bool:
    """
    检查网络连接
    
    Args:
        url: 检查的 URL
    
    Returns:
        是否连接成功
    """
    try:
        from app.core.constants import APIConstants
        response = requests.get(url, timeout=APIConstants.REQUEST_TIMEOUT)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.warning(f"网络连接检查失败: {e}")
        return False


def check_device_capabilities() -> Dict[str, Any]:
    """
    检查设备能力
    
    Returns:
        设备信息字典，包含：
        - device: 设备类型 ("cuda" 或 "cpu")
        - has_internet: 是否有网络连接
        - can_use_local_llm: 是否可以使用本地 LLM
        - can_use_local_summary: 是否可以使用本地摘要
    
    注意: torch采用延迟导入，避免在API服务启动时强制加载
    """
    # 延迟导入torch，避免在API服务中强制加载
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        # 如果torch不可用（如API服务），默认使用cpu
        logger.debug("torch不可用，默认使用cpu设备")
        device = "cpu"
    except Exception as e:
        # 处理其他可能的异常（如torch初始化失败）
        logger.warning(f"检查设备能力时发生异常: {e}，默认使用cpu设备")
        device = "cpu"
    
    device_info = {
        'device': device,
        'has_internet': check_internet(),
        'can_use_local_llm': False,
        'can_use_local_summary': False
    }
    
    if device_info['device'] == "cuda":
        device_info['can_use_local_llm'] = True
        device_info['can_use_local_summary'] = True
    elif device_info['device'] == "cpu":
        device_info['can_use_local_llm'] = False
        device_info['can_use_local_summary'] = False
    
    return device_info

