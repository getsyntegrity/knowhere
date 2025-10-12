import time
from typing import TypeVar, Generic, Optional

from pydantic import BaseModel, Field

from app.core.response.ResponseCode import ResponseCode

# 1. 定义一个泛型类型变量 T
T = TypeVar('T')




class ResponseResult(BaseModel, Generic[T]):
    """
    统一的 API 响应模型 (Pydantic 实现)
    - Generic[T] 使其支持泛型数据
    - BaseModel 提供了数据验证、序列化等功能
    """
    code: int
    msg: str
    data: Optional[T] = None  # data 可以是泛型 T，也可以是 None

    timestamps: int = Field(default_factory=lambda: int(time.time() * 1000))

    @classmethod
    def build(cls, response_code: ResponseCode, data: Optional[T] = None) -> 'ResponseResult[T]':
        return cls(code=response_code.code, msg=response_code.msg, data=data)

    @classmethod
    def build_msg(cls, code: int, msg: str) -> 'ResponseResult[None]':
        return cls(code=code, msg=msg, data=None)

    @classmethod
    def ok(cls) -> 'ResponseResult[None]':
        return cls.build(ResponseCode.SUCCESS)

    @classmethod
    def ok_data(cls, data: T) -> 'ResponseResult[T]':
        return cls.build(ResponseCode.SUCCESS, data=data)

    @classmethod
    def fail(cls, response_code: ResponseCode = ResponseCode.FAIL,
             msg: Optional[str] = None) -> 'ResponseResult[None]':
        final_msg = msg if msg is not None else response_code.msg
        return cls(code=response_code.code, msg=final_msg, data=None)