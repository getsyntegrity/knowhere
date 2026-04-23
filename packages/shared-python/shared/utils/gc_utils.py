"""Garbage-collection utilities shared across services."""
import gc

# torch is optional and only needed when CUDA cache cleanup is available.
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


def gc_collect():
    """
    Run garbage collection, including CUDA cache cleanup when torch is available.
    """
    gc.collect()
    if HAS_TORCH and torch.cuda.is_available():
        torch.cuda.empty_cache()
