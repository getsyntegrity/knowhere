from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection


def insert_contract_user(
    connection: Connection,
    *,
    user_id: str,
    name: str | None = None,
    email: str | None = None,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO "user" (id, name, email)
            VALUES (:user_id, :name, :email)
            """
        ),
        {
            "user_id": user_id,
            "name": name or f"Worker Contract User {user_id}",
            "email": email or f"{user_id}@worker-contract.knowhere.local",
        },
    )
