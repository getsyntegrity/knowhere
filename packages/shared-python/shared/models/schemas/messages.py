"""
Message Schema Definitions
For communication between API and Worker services via RabbitMQ
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BaseMessage(BaseModel):
    """Base message class"""
    job_id: str = Field(..., description="Job ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")
    message_type: str = Field(..., description="Message type")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class JobStatusUpdateMessage(BaseMessage):
    """Job status update message"""
    message_type: str = Field(default="job_status_update", description="Message type")
    status: str = Field(..., description="New status")
    previous_status: Optional[str] = Field(None, description="Previous status")
    trigger: str = Field(..., description="Status transition trigger reason")
    operator_id: Optional[str] = Field(None, description="Operator ID")
    operator_type: str = Field(default="system", description="Operator type: system/user")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Status transition metadata")


class JobProgressUpdateMessage(BaseMessage):
    """Job progress update message"""
    message_type: str = Field(default="job_progress_update", description="Message type")
    progress: int = Field(..., ge=0, le=100, description="Progress percentage (0-100)")
    message: str = Field(default="", description="Progress message text")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Progress metadata")


class JobResultMessage(BaseMessage):
    """Job result data message"""
    message_type: str = Field(default="job_result", description="Message type")
    status: str = Field(default="success", description="Processing status")
    
    # Chunks data (referenced by job_id, API reads from Redis)
    chunks_job_id: str = Field(..., description="Job ID for chunks data (for Redis lookup)")
    
    # Knowledge base data
    kb_records: Optional[List[Dict[str, Any]]] = Field(None, description="Knowledge base records list")
    
    # Result file info
    result_s3_key: str = Field(..., description="S3 key for result ZIP package")
    checksum: str = Field(..., description="File checksum")
    statistics: Optional[Dict[str, Any]] = Field(None, description="Statistics info")
    zip_size: int = Field(..., description="ZIP file size (bytes)")
    
    # Storage stats
    stored_count: int = Field(default=0, description="Number of stored records")
    delivery_mode: str = Field(default="url", description="Delivery mode")
    
    # Processing result directory (optional, for debugging)
    add_dir: Optional[str] = Field(None, description="Processing result directory path")


class JobFailureMessage(BaseMessage):
    """Job failure message"""
    message_type: str = Field(default="job_failure", description="Message type")
    error_code: str = Field(default="UNKNOWN", description="Standard error code (e.g., INVALID_ARGUMENT, INTERNAL_ERROR)")
    error_message: str = Field(..., description="Error message")
    error_type: Optional[str] = Field(None, description="Error type (Python exception class name)")
    stack_trace: Optional[str] = Field(None, description="Stack trace (internal logs only)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Error metadata")


class JobWorkloadMetricsMessage(BaseMessage):
    """Job workload metrics message - Worker reports workload, API handles billing"""
    message_type: str = Field(default="job_workload_metrics", description="Message type")
    page_count: int = Field(..., ge=1, description="Document page count (workload metric)")
    user_id: str = Field(..., description="User ID")
    filename: Optional[str] = Field(None, description="Filename")
