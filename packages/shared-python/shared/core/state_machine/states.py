"""
状态机状态枚举和转换规则 - 简化版本
"""
import os
from enum import Enum
from typing import Dict, Set


class JobStatus(str, Enum):
    """PRD任务状态枚举"""
    PENDING = "pending"
    WAITING_FILE = "waiting-file"
    RUNNING = "running"
    CONVERTING = "converting"
    DONE = "done"
    FAILED = "failed"



# 终态集合
TERMINAL_STATES: Set[str] = {JobStatus.DONE.value, JobStatus.FAILED.value}


def _get_upload_expire_seconds() -> int:
    """Read UPLOAD_EXPIRE_SECONDS from env (avoids circular import with settings)."""
    return int(os.getenv("UPLOAD_EXPIRE_SECONDS", "7200"))


# PRD状态超时配置（秒）
STATE_TIMEOUTS: Dict[str, int] = {
    JobStatus.PENDING.value: 300,        # 5分钟
    JobStatus.WAITING_FILE.value: _get_upload_expire_seconds(),
    JobStatus.RUNNING.value: 1800,       # 30分钟
    JobStatus.CONVERTING.value: 600,     # 10分钟
    JobStatus.DONE.value: 0,             # 无超时
    JobStatus.FAILED.value: 0,           # 无超时
}




def is_terminal_state(state: str) -> bool:
    """检查是否为终态"""
    return state in TERMINAL_STATES




def get_state_timeout(state: str) -> int:
    """获取状态超时时间（秒）"""
    return STATE_TIMEOUTS.get(state, 0)


# Valid state transitions — prevents illegal jumps (e.g. done → running).
# Any transition to FAILED is always allowed (not listed per-state).
VALID_TRANSITIONS: Dict[str, Set[str]] = {
    JobStatus.PENDING.value: {JobStatus.RUNNING.value, JobStatus.WAITING_FILE.value},
    JobStatus.WAITING_FILE.value: {JobStatus.PENDING.value},
    JobStatus.RUNNING.value: {JobStatus.CONVERTING.value, JobStatus.DONE.value},
    JobStatus.CONVERTING.value: {JobStatus.DONE.value},
    JobStatus.DONE.value: set(),
    JobStatus.FAILED.value: {JobStatus.PENDING.value},  # retry
}


def is_valid_transition(from_state: str, to_state: str) -> bool:
    """Check whether a state transition is allowed.

    Transitions to FAILED are always valid from any non-terminal state.
    """
    if to_state == JobStatus.FAILED.value:
        return from_state not in TERMINAL_STATES
    allowed = VALID_TRANSITIONS.get(from_state, set())
    return to_state in allowed

