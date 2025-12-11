"""
预定义的模型配置
方便快速使用不同的AI模型
"""
from typing import Dict, Any
from shared.core.config import settings


class ModelConfigs:
    """预定义的模型配置"""
    
    # DeepSeek 配置
    DEEPSEEK = {
        "api_key": settings.DS_KEY,
        "api_url": settings.DS_URL,
        "models": {
            "chat": "deepseek-chat",
            "coder": "deepseek-coder",
        }
    }
    
    # 通义千问 配置（使用阿里云API）
    QWEN = {
        "api_key": settings.ALI_API_KEY,  # 使用ALI_API_KEY
        "api_url": settings.ALI_URL,  # 使用ALI_URL
        "models": {
            "turbo": "qwen-turbo",
            "plus": "qwen-plus",
            "max": "qwen-max",
            "long": "qwen-long",
        }
    }
    
    # 智谱GLM 配置
    GLM = {
        "api_key": getattr(settings, 'GLM_API_KEY', ''),
        "api_url": getattr(settings, 'GLM_API_URL', 'https://open.bigmodel.cn/api/paas/v4/chat/completions'),
        "models": {
            "4": "glm-4",
            "4-plus": "glm-4-plus",
            "4-air": "glm-4-air",
        }
    }
    
    # OpenAI 配置
    OPENAI = {
        "api_key": settings.GPT_API_KEY,
        "api_url": "https://api.openai.com/v1/chat/completions",
        "models": {
            "gpt-4": "gpt-4",
            "gpt-4-turbo": "gpt-4-turbo",
            "gpt-3.5": "gpt-3.5-turbo",
        }
    }
    
    @classmethod
    def get_config(cls, provider: str, model_key: str = None) -> Dict[str, Any]:
        """
        获取模型配置
        
        Args:
            provider: 提供商名称 ('deepseek', 'qwen', 'glm', 'openai')
            model_key: 模型键（可选，如 'chat', 'plus' 等）
        
        Returns:
            包含 api_key, api_url, model 的字典
        """
        provider = provider.upper()
        if not hasattr(cls, provider):
            raise ValueError(f"不支持的提供商: {provider}")
        
        config = getattr(cls, provider)
        result = {
            "api_key": config["api_key"],
            "api_url": config["api_url"],
        }
        
        if model_key:
            if model_key not in config["models"]:
                raise ValueError(f"提供商 {provider} 不支持模型键: {model_key}")
            result["model"] = config["models"][model_key]
        
        return result
    
    @classmethod
    def list_providers(cls) -> Dict[str, list]:
        """列出所有支持的提供商和模型"""
        return {
            "deepseek": list(cls.DEEPSEEK["models"].keys()),
            "qwen": list(cls.QWEN["models"].keys()),
            "glm": list(cls.GLM["models"].keys()),
            "openai": list(cls.OPENAI["models"].keys()),
        }


# 快捷函数
def get_model_config(provider: str, model_key: str = None) -> Dict[str, Any]:
    """
    快捷获取模型配置
    
    示例:
        config = get_model_config('qwen', 'plus')
        # 返回: {'api_key': '...', 'api_url': '...', 'model': 'qwen-plus'}
    """
    return ModelConfigs.get_config(provider, model_key)
