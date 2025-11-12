"""
常量定义
"""
from .api import APIConstants
from .business import BusinessConstants
from .processing import ProcessingConstants
from .system import SystemConstants

__all__ = [
    'SystemConstants',
    'BusinessConstants', 
    'APIConstants',
    'ProcessingConstants'
]
