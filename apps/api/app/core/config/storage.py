"""
存储配置
"""
import boto3
from botocore.config import Config
from pydantic import Field
from pydantic import BaseModel


class StorageConfig(BaseModel):
    model_config = {"extra": "ignore"}  # 忽略额外字段
    """存储配置"""
    
    # S3存储配置
    S3_BUCKET_NAME: str = Field(..., description="S3存储桶名称")
    S3_ACCESS_KEY_ID: str = Field(..., description="S3访问密钥ID")
    S3_SECRET_ACCESS_KEY: str = Field(..., description="S3秘密访问密钥")
    S3_ENDPOINT_URL: str = Field(..., description="S3端点URL")
    S3_PRIVATE_DOMAIN: str = Field(default="", description="S3私有域名")
    S3_TEMP_PATH: str = Field(..., description="S3临时路径")
    
    # S3高级配置
    S3_REGION: str = Field(default="", description="S3区域（MinIO等可留空）")
    S3_USE_SSL: bool = Field(default=True, description="是否使用SSL连接")
    S3_ADDRESSING_STYLE: str = Field(default="auto", description="S3寻址风格：auto/path/virtual")
    
    # 文件处理配置
    MAX_FILE_SIZE: int = Field(default=104857600, description="最大文件大小（字节）")
    MAX_IMAGE_SIZE: int = Field(default=10485760, description="最大图像大小（字节）")
    SUPPORTED_EXTENSIONS: str = Field(
        default=".doc,.docx,.pdf,.txt,.xls,.xlsx,.csv,.jpg,.png", 
        description="支持的文件扩展名"
    )
    
    def get_s3_client(self) -> 'boto3.client':
        """获取S3客户端"""
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
            "endpoint_url": self.S3_ENDPOINT_URL,
        }
        
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
    
    def get_supported_extensions(self) -> list:
        """获取支持的文件扩展名列表"""
        return [ext.strip() for ext in self.SUPPORTED_EXTENSIONS.split(',')]
