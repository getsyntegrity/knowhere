"""
状态机状态枚举和转换规则 - 简化版本
"""
from enum import Enum
from typing import Dict, List, Set


class JobState(str, Enum):
    """统一任务状态枚举"""
    # 基础状态
    PENDING = "pending"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    
    # 表格填充状态
    EXTRACTING_TABLE = "extracting_table"
    TABLE_EXTRACTED = "table_extracted"
    KB_SEARCHING = "kb_searching"
    KB_SEARCHED = "kb_searched"
    LLM_PROCESSING = "llm_processing"
    LLM_PROCESSED = "llm_processed"
    FILLING_TABLE = "filling_table"
    TABLE_FILLED = "table_filled"
    GENERATING_RESULT = "generating_result"
    
    # 知识库管理状态
    PARSING = "parsing"
    PARSED = "parsed"
    CHUNKING = "chunking"
    CHUNKED = "chunked"
    VECTORIZING = "vectorizing"
    VECTORIZED = "vectorized"
    STORING_DB = "storing_db"
    DB_STORED = "db_stored"
    WEBHOOK_SENDING = "webhook_sending"


class JobStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# 表格填充状态转换规则
TABLE_FILL_TRANSITIONS: Dict[str, List[str]] = {
    JobState.PENDING.value: [JobState.UPLOADING.value, JobState.FAILED.value],
    JobState.UPLOADING.value: [JobState.UPLOADED.value, JobState.FAILED.value, JobState.UPLOADING.value],
    JobState.UPLOADED.value: [JobState.EXTRACTING_TABLE.value, JobState.FAILED.value],
    JobState.EXTRACTING_TABLE.value: [JobState.TABLE_EXTRACTED.value, JobState.FAILED.value],
    JobState.TABLE_EXTRACTED.value: [JobState.KB_SEARCHING.value, JobState.FAILED.value],
    JobState.KB_SEARCHING.value: [JobState.KB_SEARCHED.value, JobState.FAILED.value],
    JobState.KB_SEARCHED.value: [JobState.LLM_PROCESSING.value, JobState.FAILED.value],
    JobState.LLM_PROCESSING.value: [JobState.LLM_PROCESSED.value, JobState.FAILED.value],
    JobState.LLM_PROCESSED.value: [JobState.FILLING_TABLE.value, JobState.FAILED.value],
    JobState.FILLING_TABLE.value: [JobState.TABLE_FILLED.value, JobState.FAILED.value],
    JobState.TABLE_FILLED.value: [JobState.GENERATING_RESULT.value, JobState.FAILED.value],
    JobState.GENERATING_RESULT.value: [JobState.COMPLETED.value, JobState.FAILED.value],
    JobState.COMPLETED.value: [],
    JobState.FAILED.value: [JobState.PENDING.value],
}

# 知识库管理状态转换规则
KB_MANAGEMENT_TRANSITIONS: Dict[str, List[str]] = {
    JobState.PENDING.value: [JobState.UPLOADING.value, JobState.FAILED.value],
    JobState.UPLOADING.value: [JobState.UPLOADED.value, JobState.FAILED.value, JobState.UPLOADING.value],
    JobState.UPLOADED.value: [JobState.PARSING.value, JobState.FAILED.value],
    # 修复：PARSING可以直接转换到VECTORIZING，跳过PARSED/CHUNKING/CHUNKED状态
    JobState.PARSING.value: [JobState.VECTORIZING.value, JobState.FAILED.value],
    # 保留这些状态以支持未来的细化流程，但当前实现中不使用
    JobState.PARSED.value: [JobState.CHUNKING.value, JobState.FAILED.value],
    JobState.CHUNKING.value: [JobState.CHUNKED.value, JobState.FAILED.value],
    JobState.CHUNKED.value: [JobState.VECTORIZING.value, JobState.FAILED.value],
    JobState.VECTORIZING.value: [JobState.VECTORIZED.value, JobState.FAILED.value],
    JobState.VECTORIZED.value: [JobState.STORING_DB.value, JobState.FAILED.value],
    JobState.STORING_DB.value: [JobState.DB_STORED.value, JobState.FAILED.value],
    JobState.DB_STORED.value: [JobState.COMPLETED.value, JobState.FAILED.value],
    JobState.WEBHOOK_SENDING.value: [JobState.COMPLETED.value, JobState.FAILED.value],
    JobState.COMPLETED.value: [],
    JobState.FAILED.value: [JobState.PENDING.value],
}

# 默认状态转换规则（向后兼容）
JOB_TRANSITIONS: Dict[str, List[str]] = {
    JobState.PENDING.value: [JobState.UPLOADING.value, JobState.FAILED.value],
    JobState.UPLOADING.value: [JobState.UPLOADED.value, JobState.FAILED.value, JobState.UPLOADING.value],
    JobState.UPLOADED.value: [JobState.PROCESSING.value, JobState.FAILED.value],
    JobState.PROCESSING.value: [JobState.COMPLETED.value, JobState.FAILED.value, JobState.PROCESSING.value],
    JobState.COMPLETED.value: [],
    JobState.FAILED.value: [JobState.PENDING.value],
}

# 终态集合
TERMINAL_STATES: Set[str] = {JobState.COMPLETED.value, JobState.FAILED.value}

# 处理中状态集合
PROCESSING_STATES: Set[str] = {
    JobState.UPLOADING.value,
    JobState.UPLOADED.value,
    JobState.PROCESSING.value,
    # 表格填充状态
    JobState.EXTRACTING_TABLE.value,
    JobState.TABLE_EXTRACTED.value,
    JobState.KB_SEARCHING.value,
    JobState.KB_SEARCHED.value,
    JobState.LLM_PROCESSING.value,
    JobState.LLM_PROCESSED.value,
    JobState.FILLING_TABLE.value,
    JobState.TABLE_FILLED.value,
    JobState.GENERATING_RESULT.value,
    # 知识库管理状态
    JobState.PARSING.value,
    JobState.PARSED.value,
    JobState.CHUNKING.value,
    JobState.CHUNKED.value,
    JobState.VECTORIZING.value,
    JobState.VECTORIZED.value,
    JobState.STORING_DB.value,
    JobState.DB_STORED.value,
    JobState.WEBHOOK_SENDING.value,
}

# 状态超时配置（秒）
STATE_TIMEOUTS: Dict[str, int] = {
    # 基础状态
    JobState.PENDING.value: 300,      # 5分钟
    JobState.UPLOADING.value: 600,    # 10分钟
    JobState.UPLOADED.value: 60,      # 1分钟
    JobState.PROCESSING.value: 1800,  # 30分钟
    JobState.COMPLETED.value: 0,      # 无超时
    JobState.FAILED.value: 0,         # 无超时
    
    # 表格填充状态
    JobState.EXTRACTING_TABLE.value: 300,    # 5分钟
    JobState.TABLE_EXTRACTED.value: 60,      # 1分钟
    JobState.KB_SEARCHING.value: 300,        # 5分钟
    JobState.KB_SEARCHED.value: 60,          # 1分钟
    JobState.LLM_PROCESSING.value: 600,      # 10分钟
    JobState.LLM_PROCESSED.value: 60,        # 1分钟
    JobState.FILLING_TABLE.value: 300,       # 5分钟
    JobState.TABLE_FILLED.value: 60,         # 1分钟
    JobState.GENERATING_RESULT.value: 300,   # 5分钟
    
    # 知识库管理状态
    JobState.PARSING.value: 600,             # 10分钟
    JobState.PARSED.value: 60,               # 1分钟
    JobState.CHUNKING.value: 300,            # 5分钟
    JobState.CHUNKED.value: 60,              # 1分钟
    JobState.VECTORIZING.value: 1200,        # 20分钟
    JobState.VECTORIZED.value: 60,           # 1分钟
    JobState.STORING_DB.value: 600,          # 10分钟
    JobState.DB_STORED.value: 60,            # 1分钟
    JobState.WEBHOOK_SENDING.value: 300,     # 5分钟
}


def get_transitions(job_type: str) -> Dict[str, List[str]]:
    """获取指定任务类型的转换规则"""
    if job_type == "table_fill":
        return TABLE_FILL_TRANSITIONS
    elif job_type == "kb_management":
        return KB_MANAGEMENT_TRANSITIONS
    else:
        return JOB_TRANSITIONS


def is_valid_transition(job_type: str, from_state: str, to_state: str) -> bool:
    """检查状态转换是否有效"""
    transitions = get_transitions(job_type)
    return to_state in transitions.get(from_state, [])


def is_terminal_state(state: str) -> bool:
    """检查是否为终态"""
    return state in TERMINAL_STATES


def is_processing_state(state: str) -> bool:
    """检查是否为处理中状态"""
    return state in PROCESSING_STATES


def get_job_status_from_state(state: str) -> str:
    """根据详细状态获取Job顶层状态（内部使用）"""
    if not state:
        return JobStatus.PENDING.value
    
    normalized_state = state.lower()
    
    if normalized_state == JobState.FAILED.value:
        return JobStatus.FAILED.value
    if normalized_state == JobState.COMPLETED.value:
        return JobStatus.COMPLETED.value
    if normalized_state == JobState.PENDING.value:
        return JobStatus.PENDING.value
    
    return JobStatus.PROCESSING.value


def get_prd_status_from_state(state: str) -> str:
    """将内部状态映射为PRD定义的状态"""
    if not state:
        return "pending"

    normalized_state = state.lower()

    if normalized_state == JobState.FAILED.value:
        return "failed"
    if normalized_state == JobState.COMPLETED.value:
        return "done"
    if normalized_state == JobState.UPLOADING.value:
        return "waiting_for_upload"
    if normalized_state == JobState.UPLOADED.value:
        return "uploaded"
    if normalized_state == JobState.PENDING.value:
        return "pending"
    if normalized_state == JobState.PROCESSING.value:
        return "running"

    return "running"


def get_state_timeout(state: str) -> int:
    """获取状态超时时间（秒）"""
    return STATE_TIMEOUTS.get(state, 0)


def can_retry_from_state(state: str) -> bool:
    """检查状态是否支持重试"""
    if not state:
        return False
    
    # 只有处理中状态和失败状态支持重试
    return state in [JobState.UPLOADING.value, JobState.UPLOADED.value, JobState.PROCESSING.value, JobState.FAILED.value]


def get_retry_target_state(current_state: str) -> str:
    """获取重试目标状态"""
    if current_state == JobState.FAILED.value:
        return JobState.PENDING.value
    elif current_state in [JobState.UPLOADING.value, JobState.UPLOADED.value, JobState.PROCESSING.value]:
        return current_state  # 同状态重试
    else:
        return current_state