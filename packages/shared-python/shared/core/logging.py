import logging
import os
import sys

from loguru import logger


class InterceptHandler(logging.Handler):
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

def setup_logging():
    # 从环境变量获取日志级别
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # 验证日志级别
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if log_level not in valid_levels:
        log_level = "INFO"
    
    # 移除所有现有的处理器
    logger.remove()
    
    # 添加控制台输出处理器（使用环境变量设置的级别）
    logger.add(
        sys.stdout, 
        colorize=True,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    
    # 创建日志目录
    os.makedirs("logs", exist_ok=True)
    
    # 1. 生产日志文件：只记录INFO及以上级别（生产环境主要关注）
    logger.add(
        "logs/app_production_{time:YYYY-MM-DD}.log", 
        rotation="1 day", 
        retention="30 days",  # 生产日志保留30天
        compression="zip", 
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        filter=lambda record: record["level"].name in ["INFO", "WARNING", "ERROR", "CRITICAL"]
    )
    
    # 2. 调试日志文件：记录所有DEBUG级别（用于问题排查）
    logger.add(
        "logs/app_debug_{time:YYYY-MM-DD}.log", 
        rotation="1 day", 
        retention="7 days",   # 调试日志只保留7天
        compression="zip", 
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        filter=lambda record: record["level"].name == "DEBUG"
    )
    
    # 3. 错误日志文件：专门记录ERROR和CRITICAL级别
    logger.add(
        "logs/app_error_{time:YYYY-MM-DD}.log", 
        rotation="1 day", 
        retention="90 days",  # 错误日志保留90天
        compression="zip", 
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        filter=lambda record: record["level"].name in ["ERROR", "CRITICAL"]
    )

    # 配置标准logging库
    logging.basicConfig(handlers=[InterceptHandler()], level=getattr(logging, log_level), force=True)
    logging.getLogger("uvicorn.access").handlers = [InterceptHandler()]
    
    logger.info(f"Logging configured! Level: {log_level}")
    logger.info("日志文件分离: production(INFO+), debug(DEBUG), error(ERROR+)")


def get_logger(name: str):
    """获取logger实例"""
    return logger.bind(name=name)
