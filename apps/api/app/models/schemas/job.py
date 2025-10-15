"""
统一Job相关Schema（符合PRD规范）
"""
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


class WebhookConfig(BaseModel):
    """Webhook配置"""
    url: str = Field(..., description="Webhook回调URL")
    secret: str = Field(..., description="用于生成签名的密钥")


class JobCreate(BaseModel):
    """创建任务请求"""
    source_type: Literal["file", "url"] = Field(..., description="文档来源类型")
    source_url: Optional[str] = Field(None, description="文件URL（source_type=url时必填）")
    file_name: Optional[str] = Field(None, description="文件名（source_type=file时必填，需包含扩展名）")
    data_id: Optional[str] = Field(None, max_length=128, description="用户自定义ID")
    parsing_params: Optional[Dict[str, Any]] = Field(None, description="解析参数")
    webhook: Optional[WebhookConfig] = Field(None, description="Webhook配置")
    result_mode: Literal["auto", "inline", "url"] = Field("auto", description="结果返回模式")


class JobResponse(BaseModel):
    """任务响应"""
    job_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    source_type: str = Field(..., description="文件来源类型")
    data_id: Optional[str] = Field(None, description="用户自定义ID")
    created_at: datetime = Field(..., description="创建时间")
    result_mode: Literal["auto", "inline", "url"] = Field("auto", description="结果返回模式")
    
    # waiting_for_upload状态特有字段
    upload_url: Optional[str] = Field(None, description="上传URL")
    upload_headers: Optional[Dict[str, str]] = Field(None, description="上传请求头")
    expires_in: Optional[int] = Field(None, description="URL过期时间（秒）")
    
    # running状态特有字段
    progress: Optional[Dict[str, Any]] = Field(None, description="进度信息")
    
    # done状态特有字段
    result: Optional[Dict[str, Any]] = Field(None, description="解析结果")
    result_url: Optional[str] = Field(None, description="结果文件URL")
    result_metadata: Optional[Dict[str, Any]] = Field(None, description="结果元信息")
    
    # failed状态特有字段
    error: Optional[Dict[str, Any]] = Field(None, description="错误信息")


class JobStatus(BaseModel):
    """任务状态查询响应"""
    job_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    source_type: str = Field(..., description="文件来源类型")
    data_id: Optional[str] = Field(None, description="用户自定义ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    result_mode: Literal["auto", "inline", "url"] = Field("auto", description="结果返回模式")
    
    # 状态相关字段
    current_state: Optional[str] = Field(None, description="当前详细状态")
    progress: Optional[Dict[str, Any]] = Field(None, description="进度信息")
    error: Optional[Dict[str, Any]] = Field(None, description="错误信息")
    
    # 结果相关字段
    result: Optional[Dict[str, Any]] = Field(None, description="解析结果")
    result_url: Optional[str] = Field(None, description="结果文件URL")
    result_metadata: Optional[Dict[str, Any]] = Field(None, description="结果元信息")
    
    # 元数据
    file_path: Optional[str] = Field(None, description="文件路径")
    s3_key: Optional[str] = Field(None, description="S3存储键")
    webhook_url: Optional[str] = Field(None, description="Webhook URL")
    webhook_enabled: bool = Field(False, description="是否启用Webhook")


class JobList(BaseModel):
    """任务列表响应"""
    jobs: list[JobResponse] = Field(..., description="任务列表")
    total: int = Field(..., description="总数量")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")


class ConfirmUploadRequest(BaseModel):
    """确认上传请求"""
    pass  # 无需额外参数，从URL路径获取job_id
