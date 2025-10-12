"""
服务工厂类
用于管理服务实例的创建和依赖注入
"""
from app.repositories.user_repository import UserRepository
from app.services.user.user_service import UserService


class ServiceFactory:
    """服务工厂类"""
    
    _instance = None
    _user_repository = None
    _user_service = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @property
    def user_repository(self) -> UserRepository:
        """获取用户仓储实例"""
        if self._user_repository is None:
            self._user_repository = UserRepository()
        return self._user_repository
    
    @property
    def user_service(self) -> UserService:
        """获取用户服务实例"""
        if self._user_service is None:
            self._user_service = UserService(self.user_repository)
        return self._user_service


# 全局服务工厂实例
service_factory = ServiceFactory()
