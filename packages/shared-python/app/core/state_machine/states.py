"""
状态机状态枚举和转换规则 - 简化版本
"""
from enum import Enum
from typing import Dict, List, Set




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

# PRD状态超时配置（秒）
STATE_TIMEOUTS: Dict[str, int] = {
    JobStatus.PENDING.value: 300,        # 5分钟
    JobStatus.WAITING_FILE.value: 600,   # 10分钟
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

