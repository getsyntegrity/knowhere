"""
系统常量
"""
from typing import Dict, List


class SystemConstants:
    """系统级常量"""
    
    # 文件大小限制
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
    
    # 支持的文件格式
    SUPPORTED_EXTENSIONS = {
        'documents': ['.doc', '.docx', '.pdf', '.txt'],
        'spreadsheets': ['.xls', '.xlsx', '.csv'],
        'images': ['.jpg', '.jpeg', '.png', '.gif'],
        'presentations': ['.ppt', '.pptx']
    }
    
    # 环境类型
    ENVIRONMENTS = ['development', 'staging', 'production']
    
    # 日志级别
    LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
