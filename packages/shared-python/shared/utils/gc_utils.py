"""
垃圾回收工具函数
这些函数被多个服务使用，保留在 shared-python 中
"""
import gc

import torch


def gc_collect():
    """
    执行垃圾回收，包括 CUDA 缓存清理
    """
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

