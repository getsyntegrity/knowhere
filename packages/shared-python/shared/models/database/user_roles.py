from sqlalchemy import Column, ForeignKey, String, Table

from shared.core.database import Base

user_roles_association = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", String(255), ForeignKey("users.id"), primary_key=True),
    Column("role_id", String(255), ForeignKey("roles.id"), primary_key=True),
)