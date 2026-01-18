"""
存储配置
"""
import os

import boto3
from botocore.config import Config
from pydantic import BaseModel, Field, model_validator

from shared.core.exceptions.domain_exceptions import (
    DependencyMissingException,
    SystemSettingInvalidException,
    SystemSettingMissingException,
)

# Storage适配器延迟导入，避免循环依赖
# from shared.services.storage.adapters import S3StorageAdapter
# OSSStorageAdapter延迟导入，只在S3_TYPE=oss时导入


class StorageConfig(BaseModel):
    model_config = {"extra": "ignore"}  # 忽略额外字段
    """存储配置"""
    
    # 存储类型配置
    S3_TYPE: str = Field(default="s3", description="存储类型: s3, oss, minio")
    
    # S3存储配置（通用配置，所有类型共用变量名）
    S3_BUCKET_NAME: str = Field(..., description="存储桶名称")
    S3_ACCESS_KEY_ID: str = Field(..., description="访问密钥ID")
    S3_SECRET_ACCESS_KEY: str = Field(..., description="秘密访问密钥")
    S3_ENDPOINT_URL: str = Field(default="", description="端点URL（S3/MinIO使用）")
    S3_PRIVATE_DOMAIN: str = Field(default="", description="私有域名")
    S3_TEMP_PATH: str = Field(..., description="临时路径")
    
    # S3高级配置
    S3_REGION: str = Field(default="", description="S3区域（MinIO等可留空）")
    S3_USE_SSL: bool = Field(default=True, description="是否使用SSL连接")
    S3_ADDRESSING_STYLE: str = Field(default="auto", description="S3寻址风格：auto/path/virtual")
    
    # OSS专用配置（仅S3_TYPE=oss时使用）
    OSS_ENDPOINT: str = Field(default="", description="OSS端点（例如: oss-cn-hangzhou.aliyuncs.com）")
    
    # 文件处理配置
    MAX_FILE_SIZE: int = Field(default=104857600, description="最大文件大小（字节）")
    MAX_IMAGE_SIZE: int = Field(default=10485760, description="最大图像大小（字节）")
    SUPPORTED_EXTENSIONS: str = Field(
        default=".doc,.docx,.pdf,.txt,.xls,.xlsx,.csv,.jpg,.png", 
        description="支持的文件扩展名"
    )
    
    # 用户数据目录配置（API和Worker共享，必须配置绝对路径）
    USERS_DATA_PATH: str = Field(..., description="用户数据目录的绝对路径（必填）")
    
    @model_validator(mode='after')
    def _validate_users_data_path(self):
        """验证 USERS_DATA_PATH 配置"""
        if not self.USERS_DATA_PATH:
            raise SystemSettingMissingException(
                internal_message="USERS_DATA_PATH must be configured, cannot be empty"
            )
        
        # 检查是否为绝对路径
        if not os.path.isabs(self.USERS_DATA_PATH):
            raise SystemSettingInvalidException(
                internal_message=f"USERS_DATA_PATH must be an absolute path, current value: {self.USERS_DATA_PATH}"
            )
        
        # 只在目录已存在时检查可写性（不自动创建）
        if os.path.exists(self.USERS_DATA_PATH):
            if not os.access(self.USERS_DATA_PATH, os.W_OK):
                raise SystemSettingInvalidException(
                    internal_message=f"USERS_DATA_PATH directory is not writable: {self.USERS_DATA_PATH}"
                )
        
        return self
    
    # S3事件通知配置
    S3_WEBHOOK_AUTH_TOKEN: str = Field(default="", description="MinIO webhook认证token")
    SNS_SIGNATURE_VERIFICATION: bool = Field(default=True, description="是否验证SNS签名")
    
    # OSS事件通知配置
    OSS_EVENT_CALLBACK_KEY: str = Field(default="", description="OSS事件回调密钥")
    OSS_EVENT_VERIFY_SIGNATURE: bool = Field(default=True, description="是否验证OSS事件签名")
    
    def get_s3_client(self) -> 'boto3.client':
        """获取S3客户端（用于S3和MinIO）"""
        # 构建配置
        config_kwargs = {}
        
        # 配置addressing style
        if self.S3_ADDRESSING_STYLE in ['path', 'virtual']:
            config_kwargs['s3'] = {'addressing_style': self.S3_ADDRESSING_STYLE}
        
        # 配置重试策略
        config_kwargs['retries'] = {'max_attempts': 5, 'mode': 'standard'}
        
        config = Config(**config_kwargs) if config_kwargs else None
        
        # 构建客户端参数
        client_kwargs = {
            "service_name": "s3",
            "aws_access_key_id": self.S3_ACCESS_KEY_ID,
            "aws_secret_access_key": self.S3_SECRET_ACCESS_KEY,
        }
        
        # 如果有endpoint_url（MinIO或自定义S3兼容服务），则添加
        if self.S3_ENDPOINT_URL:
            client_kwargs["endpoint_url"] = self.S3_ENDPOINT_URL
        
        # 只有在指定了region时才添加region_name
        if self.S3_REGION:
            client_kwargs["region_name"] = self.S3_REGION
        
        # 配置SSL
        if not self.S3_USE_SSL:
            client_kwargs["use_ssl"] = False
        
        # 只有在有配置时才添加config
        if config:
            client_kwargs["config"] = config
        
        return boto3.client(**client_kwargs)
    
    def get_oss_bucket(self):
        """获取OSS Bucket对象"""
        # 延迟导入oss2，只在需要时导入
        try:
            import oss2
        except ImportError as e:
            raise DependencyMissingException(
                internal_message="oss2 module is not installed. When S3_TYPE=oss, please install: pip install oss2>=2.18.0",
                original_exception=e,
            ) from e
        
        if not self.OSS_ENDPOINT:
            raise SystemSettingMissingException(
                internal_message="OSS_ENDPOINT is required when S3_TYPE=oss"
            )
        
        auth = oss2.Auth(self.S3_ACCESS_KEY_ID, self.S3_SECRET_ACCESS_KEY)
        bucket = oss2.Bucket(auth, self.OSS_ENDPOINT, self.S3_BUCKET_NAME)
        return bucket
    
    def get_storage_adapter(self):
        """
        获取存储适配器（工厂方法）
        根据S3_TYPE环境变量或配置返回对应的存储适配器
        """
        storage_type = os.getenv('S3_TYPE', self.S3_TYPE).lower()
        
        if storage_type == 'oss':
            # OSS存储适配器（延迟导入）
            from shared.services.storage.adapters.oss_adapter import OSSStorageAdapter
            bucket = self.get_oss_bucket()
            return OSSStorageAdapter(bucket, self.S3_BUCKET_NAME)
        else:
            # S3存储适配器（支持AWS S3和MinIO，延迟导入）
            from shared.services.storage.adapters import S3StorageAdapter
            s3_client = self.get_s3_client()
            return S3StorageAdapter(s3_client, self.S3_BUCKET_NAME)
    
    def get_supported_extensions(self) -> list:
        """获取支持的文件扩展名列表"""
        return [ext.strip() for ext in self.SUPPORTED_EXTENSIONS.split(',')]
