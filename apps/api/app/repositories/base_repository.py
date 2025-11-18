"""
基础Repository类
提供通用的CRUD操作，其他Repository应该继承此类
"""
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import DeclarativeBase

# 定义泛型类型
ModelType = TypeVar("ModelType", bound=DeclarativeBase)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    基础Repository类，提供通用的CRUD操作
    
    Generic参数:
    - ModelType: SQLAlchemy模型类型
    - CreateSchemaType: 创建数据的Pydantic模型类型
    - UpdateSchemaType: 更新数据的Pydantic模型类型
    """
    
    def __init__(self, model: Type[ModelType]):
        """
        初始化Repository
        
        Args:
            model: SQLAlchemy模型类
        """
        self.model = model
    
    async def create(self, db: AsyncSession, obj_in: CreateSchemaType) -> ModelType:
        """
        创建新记录
        
        Args:
            db: 数据库会话
            obj_in: 创建数据的模型
            
        Returns:
            创建的模型实例
        """
        if hasattr(obj_in, 'model_dump'):
            obj_data = obj_in.model_dump()
        elif hasattr(obj_in, 'dict'):
            obj_data = obj_in.dict()
        else:
            # 如果是SQLAlchemy模型实例，直接使用其属性
            obj_data = {key: getattr(obj_in, key) for key in obj_in.__table__.columns.keys() if hasattr(obj_in, key)}
        db_obj = self.model(**obj_data)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj
    
    async def get(self, db: AsyncSession, id: Any) -> Optional[ModelType]:
        """
        根据ID获取记录
        
        Args:
            db: 数据库会话
            id: 记录ID
            
        Returns:
            模型实例或None
        """
        result = await db.execute(select(self.model).where(self.model.id == id))
        return result.scalars().first()
    
    async def get_multi(
        self, 
        db: AsyncSession, 
        skip: int = 0, 
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ModelType]:
        """
        获取多条记录
        
        Args:
            db: 数据库会话
            skip: 跳过记录数
            limit: 限制记录数
            filters: 过滤条件字典
            
        Returns:
            模型实例列表
        """
        query = select(self.model)
        
        # 应用过滤条件
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)
        
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return result.scalars().all()
    
    async def update(
        self, 
        db: AsyncSession, 
        db_obj: ModelType, 
        obj_in: UpdateSchemaType
    ) -> ModelType:
        """
        更新记录
        
        Args:
            db: 数据库会话
            db_obj: 要更新的数据库对象
            obj_in: 更新数据的模型
            
        Returns:
            更新后的模型实例
        """
        obj_data = obj_in.model_dump(exclude_unset=True) if hasattr(obj_in, 'model_dump') else obj_in.dict(exclude_unset=True)
        
        for field, value in obj_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        
        await db.commit()
        await db.refresh(db_obj)
        return db_obj
    
    async def delete(self, db: AsyncSession, id: Any) -> bool:
        """
        删除记录
        
        Args:
            db: 数据库会话
            id: 记录ID
            
        Returns:
            是否删除成功
        """
        result = await db.execute(delete(self.model).where(self.model.id == id))
        await db.commit()
        return result.rowcount > 0
    
    async def exists(self, db: AsyncSession, id: Any) -> bool:
        """
        检查记录是否存在
        
        Args:
            db: 数据库会话
            id: 记录ID
            
        Returns:
            是否存在
        """
        result = await db.execute(select(self.model).where(self.model.id == id))
        return result.scalars().first() is not None
    
    async def count(self, db: AsyncSession, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        统计记录数量
        
        Args:
            db: 数据库会话
            filters: 过滤条件字典
            
        Returns:
            记录数量
        """
        from sqlalchemy import func
        query = select(func.count(self.model.id))
        
        # 应用过滤条件
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)
        
        result = await db.execute(query)
        return result.scalar() or 0
    
    async def get_by_field(
        self, 
        db: AsyncSession, 
        field_name: str, 
        field_value: Any
    ) -> Optional[ModelType]:
        """
        根据指定字段获取记录
        
        Args:
            db: 数据库会话
            field_name: 字段名
            field_value: 字段值
            
        Returns:
            模型实例或None
        """
        if not hasattr(self.model, field_name):
            raise ValueError(f"Field '{field_name}' does not exist in model {self.model.__name__}")
        
        result = await db.execute(
            select(self.model).where(getattr(self.model, field_name) == field_value)
        )
        return result.scalars().first()
    
    async def get_multi_by_field(
        self, 
        db: AsyncSession, 
        field_name: str, 
        field_value: Any,
        skip: int = 0,
        limit: int = 100
    ) -> List[ModelType]:
        """
        根据指定字段获取多条记录
        
        Args:
            db: 数据库会话
            field_name: 字段名
            field_value: 字段值
            skip: 跳过记录数
            limit: 限制记录数
            
        Returns:
            模型实例列表
        """
        if not hasattr(self.model, field_name):
            raise ValueError(f"Field '{field_name}' does not exist in model {self.model.__name__}")
        
        result = await db.execute(
            select(self.model)
            .where(getattr(self.model, field_name) == field_value)
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()
