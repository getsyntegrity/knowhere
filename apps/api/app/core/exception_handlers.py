"""
全局异常处理器
"""
import traceback

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException


async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP异常处理器"""
    logger.error(f"HTTP异常: {exc.status_code} - {exc.detail} - 路径: {request.url}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "status_code": exc.status_code}
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """请求验证异常处理器"""
    logger.error(f"请求验证异常: {exc.errors()} - 路径: {request.url}")
    return JSONResponse(
        status_code=422,
        content={"detail": "请求参数验证失败", "errors": exc.errors()}
    )


async def general_exception_handler(request: Request, exc: Exception):
    """通用异常处理器"""
    # 记录详细的异常信息
    logger.error(
        f"未处理的异常: {type(exc).__name__}: {str(exc)} - 路径: {request.url}",
        exc_info=True
    )
    
    # 记录完整的堆栈跟踪
    logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器内部错误",
            "status_code": 500,
            "error_type": type(exc).__name__
        }
    )


def setup_exception_handlers(app):
    """设置异常处理器"""
    # 添加HTTP异常处理器
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    
    # 添加请求验证异常处理器
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    
    # 添加通用异常处理器（捕获所有未处理的异常）
    app.add_exception_handler(Exception, general_exception_handler)
    
    logger.info("全局异常处理器已设置")
