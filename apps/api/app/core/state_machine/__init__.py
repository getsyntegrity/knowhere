"""
状态机模块
"""
from .manager import JobStateMachine
from .states import JobState, JobStatus, get_prd_status_from_state, get_job_status_from_state
from .state_machine_service import StateMachineService
from .state_sync_service import StateSyncService
from .state_timeout_service import StateTimeoutService

# 为了向后兼容，提供旧的枚举别名
# 这些将在未来版本中移除
class TableFillState:
    PENDING = JobState.PENDING
    UPLOADING = JobState.UPLOADING
    UPLOADED = JobState.UPLOADED
    PROCESSING = JobState.PROCESSING
    COMPLETED = JobState.COMPLETED
    FAILED = JobState.FAILED
    # 表格填充专用状态
    EXTRACTING_TABLE = JobState.EXTRACTING_TABLE
    TABLE_EXTRACTED = JobState.TABLE_EXTRACTED
    KB_SEARCHING = JobState.KB_SEARCHING
    KB_SEARCHED = JobState.KB_SEARCHED
    LLM_PROCESSING = JobState.LLM_PROCESSING
    LLM_PROCESSED = JobState.LLM_PROCESSED
    FILLING_TABLE = JobState.FILLING_TABLE
    TABLE_FILLED = JobState.TABLE_FILLED
    GENERATING_RESULT = JobState.GENERATING_RESULT

class KBManagementState:
    PENDING = JobState.PENDING
    UPLOADING = JobState.UPLOADING
    UPLOADED = JobState.UPLOADED
    PROCESSING = JobState.PROCESSING
    COMPLETED = JobState.COMPLETED
    FAILED = JobState.FAILED
    # 知识库管理专用状态
    PARSING = JobState.PARSING
    PARSED = JobState.PARSED
    CHUNKING = JobState.CHUNKING
    CHUNKED = JobState.CHUNKED
    VECTORIZING = JobState.VECTORIZING
    VECTORIZED = JobState.VECTORIZED
    STORING_DB = JobState.STORING_DB
    DB_STORED = JobState.DB_STORED
    WEBHOOK_SENDING = JobState.WEBHOOK_SENDING

__all__ = [
    "JobStateMachine",
    "JobState", 
    "JobStatus",
    "get_prd_status_from_state",
    "get_job_status_from_state",
    "StateMachineService",
    "StateSyncService", 
    "StateTimeoutService",
    # 向后兼容
    "TableFillState",
    "KBManagementState"
]