"""
统一存储适配器接口
支持S3、OSS和MinIO的统一访问接口
"""
from abc import ABC, abstractmethod
from typing import Optional, BinaryIO, Iterator, Dict, Any
from pathlib import Path


class StorageAdapter(ABC):
    """存储适配器抽象基类"""
    
    @abstractmethod
    def upload_file(self, local_path: str, key: str, bucket: Optional[str] = None) -> Dict[str, Any]:
        """
        上传本地文件到存储
        
        Args:
            local_path: 本地文件路径
            key: 存储中的对象键
            bucket: 存储桶名称（如果为None则使用默认bucket）
            
        Returns:
            上传结果信息
        """
        pass
    
    @abstractmethod
    def upload_fileobj(self, file_obj: BinaryIO, key: str, bucket: Optional[str] = None, 
                      content_type: Optional[str] = None) -> Dict[str, Any]:
        """
        上传文件对象到存储
        
        Args:
            file_obj: 文件对象（可读的二进制流）
            key: 存储中的对象键
            bucket: 存储桶名称（如果为None则使用默认bucket）
            content_type: 内容类型
            
        Returns:
            上传结果信息
        """
        pass
    
    @abstractmethod
    def download_file(self, key: str, local_path: str, bucket: Optional[str] = None) -> str:
        """
        从存储下载文件到本地
        
        Args:
            key: 存储中的对象键
            local_path: 本地文件路径
            bucket: 存储桶名称（如果为None则使用默认bucket）
            
        Returns:
            本地文件路径
        """
        pass
    
    @abstractmethod
    def download_fileobj(self, key: str, bucket: Optional[str] = None) -> bytes:
        """
        从存储下载文件对象
        
        Args:
            key: 存储中的对象键
            bucket: 存储桶名称（如果为None则使用默认bucket）
            
        Returns:
            文件内容（字节）
        """
        pass
    
    @abstractmethod
    def delete_object(self, key: str, bucket: Optional[str] = None) -> bool:
        """
        删除存储中的对象
        
        Args:
            key: 存储中的对象键
            bucket: 存储桶名称（如果为None则使用默认bucket）
            
        Returns:
            是否删除成功
        """
        pass
    
    @abstractmethod
    def list_objects(self, prefix: str = "", bucket: Optional[str] = None) -> Iterator[str]:
        """
        列出存储中的对象
        
        Args:
            prefix: 对象键前缀
            bucket: 存储桶名称（如果为None则使用默认bucket）
            
        Yields:
            对象键
        """
        pass
    
    @abstractmethod
    def generate_presigned_url(self, key: str, expiration: int = 3600, 
                              bucket: Optional[str] = None, method: str = "GET") -> str:
        """
        生成预签名URL
        
        Args:
            key: 存储中的对象键
            expiration: 过期时间（秒）
            bucket: 存储桶名称（如果为None则使用默认bucket）
            method: HTTP方法（GET/PUT）
            
        Returns:
            预签名URL
        """
        pass
    
    @abstractmethod
    def exists(self, key: str, bucket: Optional[str] = None) -> bool:
        """
        检查对象是否存在
        
        Args:
            key: 存储中的对象键
            bucket: 存储桶名称（如果为None则使用默认bucket）
            
        Returns:
            对象是否存在
        """
        pass
    
    @abstractmethod
    def get_object_size(self, key: str, bucket: Optional[str] = None) -> Optional[int]:
        """
        获取对象大小
        
        Args:
            key: 存储中的对象键
            bucket: 存储桶名称（如果为None则使用默认bucket）
            
        Returns:
            对象大小（字节），如果不存在返回None
        """
        pass

