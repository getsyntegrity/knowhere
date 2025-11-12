from enum import Enum
from typing import Dict


class ResponseCode(Enum):
    """
    响应状态码枚举。
    """
    SUCCESS = (200, "操作成功")
    FAIL = (1, "操作失败")
    SYSTEM_DATA_FAIL = (2, "数据操作格式异常")
    SYSTEM_PARAM_FAIL = (3, "参数错误")
    AUTHORIZATION_EXCEPTION = (401, "身份异常")

    def __init__(self, code: int, msg: str):
        self._code = code
        self._msg = msg


    @property
    def code(self) -> int:
        return self._code

    @property
    def msg(self) -> str:
        return self._msg

    @classmethod
    def get_all_as_dict(cls) -> Dict[int, str]:
        """
        获取所有响应码及其消息，以字典形式返回。
        这等同于 Java 中的 getArrayMessage()。
        """
        # 使用字典推导式，这是创建字典的最高效、最 Pythonic 的方式
        return {member.code: member.msg for member in cls}

IS_TEST_MODE = False
if __name__ == "__main__":
    if IS_TEST_MODE:
        # 1. 访问枚举成员
        success_code = ResponseCode.SUCCESS
        print(f"成员: {success_code}")
        # 输出: 成员: ResponseCode.SUCCESS

        # 2. 访问成员的属性 (code 和 msg)
        print(f"代码: {success_code.code}, 消息: {success_code.msg}")
        # 输出: 代码: 0, 消息: 操作成功

        fail_code = ResponseCode.FAIL
        print(f"代码: {fail_code.code}, 消息: {fail_code.msg}")
        # 输出: 代码: 1, 消息: 操作失败

        # 3. 遍历所有枚举成员
        print("\n--- 所有响应码 ---")
        for member in ResponseCode:
            print(f"{member.name}: code={member.code}, msg='{member.msg}'")

        # 4. 调用类方法获取字典
        all_messages = ResponseCode.get_all_as_dict()
        print("\n--- 字典形式 ---")
        import json
        print(json.dumps(all_messages, indent=2, ensure_ascii=False))
