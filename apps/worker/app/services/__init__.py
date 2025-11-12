"""
知识库服务模块
"""
# 延迟导入，避免在路径扩展前触发导入错误
# KBOrchestrator 将在需要时通过延迟导入获取

__all__ = ["KBOrchestrator"]

def __getattr__(name):
    """延迟导入 KBOrchestrator"""
    if name == "KBOrchestrator":
        from .kb_orchestrator import KBOrchestrator
        return KBOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")