"""
状态机状态枚举和转换规则
"""
from enum import Enum
from typing import Dict, List, Set


class TableFillState(str, Enum):
    """表格填充状态枚举"""
    PENDING = "pending"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    EXTRACTING_TABLE = "extracting_table"
    TABLE_EXTRACTED = "table_extracted"
    KB_SEARCHING = "kb_searching"
    KB_SEARCHED = "kb_searched"
    LLM_PROCESSING = "llm_processing"
    LLM_PROCESSED = "llm_processed"
    FILLING_TABLE = "filling_table"
    TABLE_FILLED = "table_filled"
    GENERATING_RESULT = "generating_result"
    COMPLETED = "completed"
    FAILED = "failed"


class KBManagementState(str, Enum):
    """知识库管理状态枚举"""
    PENDING = "pending"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    CHUNKING = "chunking"
    CHUNKED = "chunked"
    VECTORIZING = "vectorizing"
    VECTORIZED = "vectorized"
    STORING_DB = "storing_db"
    DB_STORED = "db_stored"
    WEBHOOK_SENDING = "webhook_sending"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStatus(str, Enum):
    """Job顶层状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# 状态转换规则
TABLE_FILL_TRANSITIONS: Dict[str, List[str]] = {
    TableFillState.PENDING.value: [TableFillState.UPLOADING.value, TableFillState.FAILED.value, TableFillState.PENDING.value],  # 支持重新启动工作流
    TableFillState.UPLOADING.value: [TableFillState.UPLOADED.value, TableFillState.FAILED.value, TableFillState.UPLOADING.value, TableFillState.PENDING.value],  # 支持重试
    TableFillState.UPLOADED.value: [TableFillState.EXTRACTING_TABLE.value, TableFillState.FAILED.value, TableFillState.PENDING.value],  # 支持重试回到pending
    TableFillState.EXTRACTING_TABLE.value: [TableFillState.TABLE_EXTRACTED.value, TableFillState.FAILED.value, TableFillState.EXTRACTING_TABLE.value, TableFillState.UPLOADED.value],  # 支持重试
    TableFillState.TABLE_EXTRACTED.value: [TableFillState.KB_SEARCHING.value, TableFillState.FAILED.value, TableFillState.UPLOADED.value],  # 支持重试回到uploaded
    TableFillState.KB_SEARCHING.value: [TableFillState.KB_SEARCHED.value, TableFillState.FAILED.value, TableFillState.KB_SEARCHING.value, TableFillState.TABLE_EXTRACTED.value],  # 支持重试
    TableFillState.KB_SEARCHED.value: [TableFillState.LLM_PROCESSING.value, TableFillState.FAILED.value, TableFillState.TABLE_EXTRACTED.value],  # 支持重试回到table_extracted
    TableFillState.LLM_PROCESSING.value: [TableFillState.LLM_PROCESSED.value, TableFillState.FAILED.value, TableFillState.LLM_PROCESSING.value, TableFillState.KB_SEARCHED.value],  # 支持重试
    TableFillState.LLM_PROCESSED.value: [TableFillState.FILLING_TABLE.value, TableFillState.FAILED.value, TableFillState.KB_SEARCHED.value],  # 支持重试回到kb_searched
    TableFillState.FILLING_TABLE.value: [TableFillState.TABLE_FILLED.value, TableFillState.FAILED.value, TableFillState.FILLING_TABLE.value, TableFillState.LLM_PROCESSED.value],  # 支持重试
    TableFillState.TABLE_FILLED.value: [TableFillState.GENERATING_RESULT.value, TableFillState.FAILED.value, TableFillState.LLM_PROCESSED.value],  # 支持重试回到llm_processed
    TableFillState.GENERATING_RESULT.value: [TableFillState.COMPLETED.value, TableFillState.FAILED.value, TableFillState.GENERATING_RESULT.value, TableFillState.TABLE_FILLED.value],  # 支持重试
    TableFillState.FAILED.value: [TableFillState.PENDING.value],  # 失败后可以重试回到pending
}

KB_MANAGEMENT_TRANSITIONS: Dict[str, List[str]] = {
    KBManagementState.PENDING.value: [KBManagementState.UPLOADING.value, KBManagementState.FAILED.value],
    KBManagementState.UPLOADING.value: [KBManagementState.UPLOADED.value, KBManagementState.FAILED.value, KBManagementState.UPLOADING.value],  # 支持重试
    KBManagementState.UPLOADED.value: [KBManagementState.PARSING.value, KBManagementState.FAILED.value],
    # 解析和向量化合并
    KBManagementState.PARSING.value: [KBManagementState.VECTORIZING.value, KBManagementState.FAILED.value, KBManagementState.PARSING.value],  # 支持重试
    KBManagementState.VECTORIZING.value: [KBManagementState.VECTORIZED.value, KBManagementState.FAILED.value, KBManagementState.VECTORIZING.value],  # 支持重试
    # 存储完成即标记为completed
    KBManagementState.VECTORIZED.value: [KBManagementState.STORING_DB.value, KBManagementState.FAILED.value],
    KBManagementState.STORING_DB.value: [KBManagementState.DB_STORED.value, KBManagementState.FAILED.value, KBManagementState.STORING_DB.value],  # 支持重试
    KBManagementState.DB_STORED.value: [KBManagementState.COMPLETED.value, KBManagementState.FAILED.value],
    # 失败状态可以重试回到pending
    KBManagementState.FAILED.value: [KBManagementState.PENDING.value],
}

# 终态集合
TERMINAL_STATES: Set[str] = {TableFillState.COMPLETED.value, TableFillState.FAILED.value,
                            KBManagementState.COMPLETED.value, KBManagementState.FAILED.value,
                            "completed", "failed"}

# 处理中状态集合
PROCESSING_STATES: Set[str] = {
    TableFillState.UPLOADING.value, TableFillState.EXTRACTING_TABLE.value, 
    TableFillState.KB_SEARCHING.value, TableFillState.LLM_PROCESSING.value,
    TableFillState.FILLING_TABLE.value, TableFillState.GENERATING_RESULT.value,
    KBManagementState.UPLOADING.value, KBManagementState.PARSING.value,
    KBManagementState.CHUNKING.value, KBManagementState.VECTORIZING.value,
    KBManagementState.STORING_DB.value, KBManagementState.WEBHOOK_SENDING.value
}


def get_transitions(job_type: str) -> Dict[str, List[str]]:
    """获取指定任务类型的转换规则"""
    if job_type == "table_fill":
        return TABLE_FILL_TRANSITIONS
    elif job_type == "kb_management":
        return KB_MANAGEMENT_TRANSITIONS
    else:
        return {}


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
        return "pending"
    normalized_state = state.lower()
    if normalized_state in {"failed", KBManagementState.FAILED.value, TableFillState.FAILED.value}:
        return "failed"
    if normalized_state in {"completed", KBManagementState.COMPLETED.value, TableFillState.COMPLETED.value}:
        return "completed"
    if normalized_state == "pending":
        return "pending"
    return "processing"


def get_prd_status_from_state(state: str) -> str:
    """将内部状态映射为PRD定义的状态"""
    if not state:
        return "pending"

    normalized_state = state.lower()

    if normalized_state in {"failed", KBManagementState.FAILED.value, TableFillState.FAILED.value}:
        return "failed"
    if normalized_state in {"completed", KBManagementState.COMPLETED.value, TableFillState.COMPLETED.value}:
        return "done"

    waiting_states = {
        "waiting_for_upload",
        TableFillState.UPLOADING.value,
        KBManagementState.UPLOADING.value
    }
    if normalized_state in waiting_states:
        return "waiting_for_upload"

    pending_states = {
        "pending",
        TableFillState.PENDING.value,
        KBManagementState.PENDING.value,
        TableFillState.UPLOADED.value,
        KBManagementState.UPLOADED.value
    }
    if normalized_state in pending_states:
        return "pending"

    converting_states = {
        "converting",
        KBManagementState.PARSING.value,
        KBManagementState.PARSED.value,
        KBManagementState.CHUNKING.value,
        KBManagementState.CHUNKED.value,
        TableFillState.EXTRACTING_TABLE.value,
        TableFillState.TABLE_EXTRACTED.value
    }
    if normalized_state in converting_states:
        return "converting"

    running_states = {
        "processing",
        "running",
        KBManagementState.VECTORIZING.value,
        KBManagementState.VECTORIZED.value,
        KBManagementState.STORING_DB.value,
        KBManagementState.DB_STORED.value,
        KBManagementState.WEBHOOK_SENDING.value,
        TableFillState.KB_SEARCHING.value,
        TableFillState.KB_SEARCHED.value,
        TableFillState.LLM_PROCESSING.value,
        TableFillState.LLM_PROCESSED.value,
        TableFillState.FILLING_TABLE.value,
        TableFillState.TABLE_FILLED.value,
        TableFillState.GENERATING_RESULT.value
    }
    if normalized_state in running_states:
        return "running"

    return "running"
