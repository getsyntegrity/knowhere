from enum import Enum
from typing import Dict


class ResponseCode(Enum):
    """Response status-code enum."""

    SUCCESS = (200, "Operation succeeded")
    FAIL = (1, "Operation failed")
    SYSTEM_DATA_FAIL = (2, "Invalid data operation format")
    SYSTEM_PARAM_FAIL = (3, "Invalid parameter")
    AUTHORIZATION_EXCEPTION = (401, "Authorization error")

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
        """Return all response codes and messages as a dictionary."""

        return {member.code: member.msg for member in cls}


IS_TEST_MODE = False


if __name__ == "__main__":
    if IS_TEST_MODE:
        # 1. Access an enum member.
        success_code = ResponseCode.SUCCESS
        print(f"Member: {success_code}")
        # Output: Member: ResponseCode.SUCCESS

        # 2. Access member attributes (code and msg).
        print(f"Code: {success_code.code}, Message: {success_code.msg}")
        # Output: Code: 200, Message: Operation succeeded

        fail_code = ResponseCode.FAIL
        print(f"Code: {fail_code.code}, Message: {fail_code.msg}")
        # Output: Code: 1, Message: Operation failed

        # 3. Iterate over all enum members.
        print("\n--- All Response Codes ---")
        for member in ResponseCode:
            print(f"{member.name}: code={member.code}, msg='{member.msg}'")

        # 4. Call the class method to get a dictionary.
        all_messages = ResponseCode.get_all_as_dict()
        print("\n--- Dictionary Form ---")
        import json

        print(json.dumps(all_messages, indent=2, ensure_ascii=False))
