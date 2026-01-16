"""
垃圾回收工具函数
这些函数被多个服务使用，保留在 shared-python 中
"""
import gc

# torch 是可选依赖，只在需要 CUDA 清理时使用
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


def gc_collect():
    """
    执行垃圾回收，包括 CUDA 缓存清理（如果 torch 可用）
    """
    gc.collect()
    if HAS_TORCH and torch.cuda.is_available():
        torch.cuda.empty_cache()

