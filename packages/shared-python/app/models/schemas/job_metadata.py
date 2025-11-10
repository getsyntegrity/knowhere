"""
Job元数据Schema定义
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class JobMetadataBase(BaseModel):
    """Job元数据基础类"""
    
    # 核心字段（创建时设置）
    original_request: Optional[Dict[str, Any]] = Field(None, description="完整的JobCreate请求")
    parsing_params: Optional[Dict[str, Any]] = Field(None, description="解析参数")
    data_id: Optional[str] = Field(None, description="用户自定义ID")
    webhook: Optional[Dict[str, Any]] = Field(None, description="Webhook配置")
    # result_mode 已移除，不再支持
    
    # 文件相关字段
    source_type: Optional[str] = Field(None, description="来源类型")
    source_file_name: Optional[str] = Field(None, description="源文件名")
    source_url: Optional[str] = Field(None, description="源URL")
    file_url: Optional[str] = Field(None, description="文件URL")
    
    # 用户配置（创建时初始化）
    user_config: Optional[Dict[str, Any]] = Field(None, description="用户配置")
    
    class Config:
        extra = "allow"


class JobMetadataHelper:
    """Job元数据辅助类"""
    
    @staticmethod
    def create_from_request(request, user_config: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """从JobCreate请求创建metadata（包含user_config）"""
        metadata = {
            "original_request": request.model_dump(),
            "parsing_params": request.parsing_params.model_dump() if request.parsing_params else None,
            "data_id": request.data_id,
            "webhook": request.webhook.model_dump() if request.webhook else None,
            # result_mode 已移除，不再支持
            "user_config": user_config,
        }
        metadata.update(kwargs)
        return metadata
    
    @staticmethod
    def get_field(metadata: Optional[Dict[str, Any]], field: str, default: Any = None) -> Any:
        """安全获取字段"""
        if not metadata:
            return default
        return metadata.get(field, default)
    
    @staticmethod
    def get_parsing_param(metadata: Optional[Dict[str, Any]], param: str, default: Any = None) -> Any:
        """从parsing_params获取参数"""
        if not metadata:
            return default
        
        parsing_params = metadata.get("parsing_params")
        if parsing_params and isinstance(parsing_params, dict):
            if param in parsing_params:
                return parsing_params.get(param, default)
        
        # 向后兼容
        if param in metadata:
            return metadata.get(param, default)
        
        return default
    
    @staticmethod
    def get_user_config(metadata: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """获取user_config"""
        return JobMetadataHelper.get_field(metadata, "user_config")
    
    @staticmethod
    def get_webhook(metadata: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """获取webhook配置"""
        return JobMetadataHelper.get_field(metadata, "webhook")
