
from typing import Optional

from shared.core.response.ResponseCode import ResponseCode


class RequestException(Exception):
    """
    自定义业务异常类。
    Attributes:
        code (int): 错误代码，
        msg (str): 错误消息。
        original_exception (Optional[Exception]): 可选的，用于包装和传递原始的底层异常。
    """

    def __init__(self, msg: str, code: int, original_exception: Optional[Exception] = None):
        super().__init__(f"[Code: {code}] {msg}")
        self.code = code
        self.msg = msg
        self.original_exception = original_exception

    def __str__(self) -> str:
        """
        自定义异常的字符串表示，使其更具可读性。
        """
        if self.original_exception:
            return f"RequestException(code={self.code}, msg='{self.msg}', original_exception={self.original_exception!r})"
        return f"RequestException(code={self.code}, msg='{self.msg}')"


    @classmethod
    def from_response_code(
            cls,
            response_code: ResponseCode,
            original_exception: Optional[Exception] = None
    ) -> 'RequestException':
        return cls(
            msg=response_code.msg,
            code=response_code.code,
            original_exception=original_exception
        )

    @classmethod
    def auth_fail(cls, msg: Optional[str] = None) -> 'RequestException':
        """
        认证失败异常。
        """

        final_msg = msg if msg is not None else ResponseCode.AUTHORIZATION_EXCEPTION.msg
        return cls(
            msg=final_msg,
            code=ResponseCode.AUTHORIZATION_EXCEPTION.code
        )

    @classmethod
    def fail(
            cls,
            msg: Optional[str] = None,
            original_exception: Optional[Exception] = None
    ) -> 'RequestException':
        """
        通用的操作失败异常。
        """
        final_msg = msg if msg is not None else ResponseCode.FAIL.msg
        return cls(
            msg=final_msg,
            code=ResponseCode.FAIL.code,
            original_exception=original_exception
        )

    @classmethod
    def from_details(
            cls,
            code: int,
            msg: str,
            original_exception: Optional[Exception] = None
    ) -> 'RequestException':
        """
        通过详细的 code 和 msg 创建一个异常。
        """
        return cls(
            code=code,
            msg=msg,
            original_exception=original_exception
        )

# --- 使用示例 ---

def risky_operation(should_fail: bool):
    if should_fail:
        # 抛出一个通用的失败异常
        raise RequestException.fail("操作数据库时发生错误")


def another_risky_operation():
    try:
        result = 10 / 0
    except ZeroDivisionError as e:
        # 包装原始异常，并抛出自定义异常
        # 这对于调试非常有用，可以保留原始的错误堆栈
        raise RequestException.from_response_code(ResponseCode.SYSTEM_DATA_FAIL, original_exception=e)


IS_TEST_MODE = False
if __name__ == "__main__":
    if IS_TEST_MODE:
        try:
            risky_operation(True)
        except RequestException as e:
            print(f"  消息: {e.msg}")
            print(f"  代码: {e.code}")
            print(f"  str(e): {e}")

        print("\n" + "-" * 20 + "\n")

        # 场景2：捕获一个包装了原始异常的业务异常
        try:
            another_risky_operation()
        except RequestException as e:
            print(f"  消息: {e.msg}")
            print(f"  代码: {e.code}")
            print(f"  原始异常: {e.original_exception}")
            print(f"  str(e): {e}")

        print("\n" + "-" * 20 + "\n")

        # 场景3：创建一个认证失败异常
        auth_error = RequestException.auth_fail("您的Token已失效")
        print(f"创建的认证异常: {auth_error}")