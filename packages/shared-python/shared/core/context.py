import contextvars
from typing import Any, Optional

_current_user_context: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar('current_user', default=None)

def set_current_user(user_data: Any):
    _current_user_context.set(user_data)

def get_current_user() -> Optional[Any]:
    """从全局上下文获取当前用户"""
    return _current_user_context.get()
