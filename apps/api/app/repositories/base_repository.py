"""Base repository helpers.

Provides common CRUD operations for repository subclasses.
"""

from collections.abc import Mapping
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import DeclarativeBase

# Generic type definitions.
ModelType = TypeVar("ModelType", bound=DeclarativeBase)
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")


class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    Base repository class with common CRUD operations.

    Generic parameters:
    - ModelType: SQLAlchemy model type
    - CreateSchemaType: Pydantic type used for creation
    - UpdateSchemaType: Pydantic type used for updates
    """

    def __init__(self, model: Type[ModelType]):
        """
        Initialize the repository.

        Args:
            model: SQLAlchemy model class.
        """
        self.model = model

    async def create(self, db: AsyncSession, obj_in: CreateSchemaType) -> ModelType:
        """
        Create a new record.

        Args:
            db: Database session.
            obj_in: Input model for creation.

        Returns:
            Created model instance.
        """
        obj_data: dict[str, Any]
        if isinstance(obj_in, BaseModel):
            obj_data = obj_in.model_dump()
        elif isinstance(obj_in, Mapping):
            obj_data = dict(obj_in)
        else:
            table = getattr(obj_in, "__table__", None)
            if table is None:
                raise TypeError(
                    f"Unsupported create payload for {self.model.__name__}: {type(obj_in)!r}"
                )
            # If this is already a SQLAlchemy model instance, reuse its fields.
            obj_data = {
                key: getattr(obj_in, key)
                for key in table.columns.keys()
                if hasattr(obj_in, key)
            }
        db_obj = self.model(**obj_data)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def get(self, db: AsyncSession, id: Any) -> Optional[ModelType]:
        """
        Get a record by ID.

        Args:
            db: Database session.
            id: Record ID.

        Returns:
            Model instance or None.
        """
        model_id = getattr(self.model, "id", None)
        if model_id is None:
            raise AttributeError(f"Model {self.model.__name__} does not define an id")
        result = await db.execute(select(self.model).where(model_id == id))
        return result.scalars().first()

    async def get_multi(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[ModelType]:
        """
        Get multiple records.

        Args:
            db: Database session.
            skip: Number of records to skip.
            limit: Maximum records to return.
            filters: Field-equality filters.

        Returns:
            Model instance list.
        """
        query = select(self.model)

        # Apply field filters.
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def update(
        self, db: AsyncSession, db_obj: ModelType, obj_in: UpdateSchemaType
    ) -> ModelType:
        """
        Update a record.

        Args:
            db: Database session.
            db_obj: Database object to update.
            obj_in: Input model with updated fields.

        Returns:
            Updated model instance.
        """
        if isinstance(obj_in, BaseModel):
            obj_data = obj_in.model_dump(exclude_unset=True)
        elif isinstance(obj_in, Mapping):
            obj_data = dict(obj_in)
        else:
            raise TypeError(
                f"Unsupported update payload for {self.model.__name__}: {type(obj_in)!r}"
            )

        for field, value in obj_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def delete(self, db: AsyncSession, id: Any) -> bool:
        """
        Delete a record.

        Args:
            db: Database session.
            id: Record ID.

        Returns:
            Whether the delete succeeded.
        """
        model_id = getattr(self.model, "id", None)
        if model_id is None:
            raise AttributeError(f"Model {self.model.__name__} does not define an id")
        result = await db.execute(delete(self.model).where(model_id == id))
        await db.commit()
        return result.rowcount > 0

    async def exists(self, db: AsyncSession, id: Any) -> bool:
        """
        Check whether a record exists.

        Args:
            db: Database session.
            id: Record ID.

        Returns:
            Whether the record exists.
        """
        model_id = getattr(self.model, "id", None)
        if model_id is None:
            raise AttributeError(f"Model {self.model.__name__} does not define an id")
        result = await db.execute(select(self.model).where(model_id == id))
        return result.scalars().first() is not None

    async def count(
        self, db: AsyncSession, filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Count matching records.

        Args:
            db: Database session.
            filters: Field-equality filters.

        Returns:
            Record count.
        """
        from sqlalchemy import func

        model_id = getattr(self.model, "id", None)
        if model_id is None:
            raise AttributeError(f"Model {self.model.__name__} does not define an id")
        query = select(func.count(model_id))

        # Apply field filters.
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)

        result = await db.execute(query)
        return result.scalar() or 0

    async def get_by_field(
        self, db: AsyncSession, field_name: str, field_value: Any
    ) -> Optional[ModelType]:
        """
        Get a record by a specific field.

        Args:
            db: Database session.
            field_name: Field name.
            field_value: Field value.

        Returns:
            Model instance or None.
        """
        if not hasattr(self.model, field_name):
            raise ValueError(
                f"Field '{field_name}' does not exist in model {self.model.__name__}"
            )

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
        limit: int = 100,
    ) -> List[ModelType]:
        """
        Get multiple records by a specific field.

        Args:
            db: Database session.
            field_name: Field name.
            field_value: Field value.
            skip: Number of records to skip.
            limit: Maximum records to return.

        Returns:
            Model instance list.
        """
        if not hasattr(self.model, field_name):
            raise ValueError(
                f"Field '{field_name}' does not exist in model {self.model.__name__}"
            )

        result = await db.execute(
            select(self.model)
            .where(getattr(self.model, field_name) == field_value)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())
