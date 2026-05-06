from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import secrets
import sys
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.core.billing import MicroDollar
from shared.core.config import settings
from shared.core.database import engine, get_db_context
from shared.models.database.api_key import APIKey
from shared.models.database.user import User
from shared.models.database.user_balance import UserBalance
from shared.services.auth.user_table_bootstrap import ensure_better_auth_user_table

_DEFAULT_API_KEY_NAME: str = "standalone-api-key"
_DEFAULT_USER_TIER: str = "free"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create or fetch an API-only standalone user and generate an API key."
        ),
    )
    parser.add_argument("--email", required=True, help="User email address.")
    parser.add_argument("--name", default="", help="Display name for new users.")
    parser.add_argument(
        "--key-name",
        default=_DEFAULT_API_KEY_NAME,
        help="Display name prefix for the generated API key.",
    )
    parser.add_argument(
        "--tier",
        default=_DEFAULT_USER_TIER,
        help="Compatibility user tier to store in user_balances.",
    )
    return parser


async def _ensure_user_table() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(ensure_better_auth_user_table)


async def _find_or_create_user(
    session: AsyncSession,
    *,
    email: str,
    name: str,
) -> User:
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("email must not be empty")

    result = await session.execute(
        select(User).where(User.email == normalized_email).limit(1)
    )
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(
        id=f"user_{uuid4().hex[:24]}",
        name=name.strip() or normalized_email,
        email=normalized_email,
    )
    session.add(user)
    await session.flush()
    return user


async def _ensure_user_balance(
    session: AsyncSession,
    *,
    user_id: str,
    tier: str,
) -> None:
    balance = await session.get(UserBalance, user_id)
    if balance is not None:
        return

    session.add(
        UserBalance(
            user_id=user_id,
            user_tier=tier,
            credits_balance=MicroDollar.from_dollars(
                settings.FREE_PLAN_INITIAL_CREDITS
            ).amount,
        )
    )


async def _resolve_key_name(
    session: AsyncSession,
    *,
    user_id: str,
    requested_name: str,
) -> str:
    key_name = requested_name.strip() or _DEFAULT_API_KEY_NAME
    existing_names = set(
        (
            await session.execute(
                select(APIKey.name).where(APIKey.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    if key_name not in existing_names:
        return key_name

    suffix = 2
    while f"{key_name}-{suffix}" in existing_names:
        suffix += 1
    return f"{key_name}-{suffix}"


def _generate_api_key() -> str:
    return f"sk_kn_{secrets.token_hex(16)}"


def _mask_api_key(api_key: str) -> str:
    if len(api_key) < 12:
        return api_key
    return api_key[:8] + "•" * (len(api_key) - 12) + api_key[-4:]


async def _create_api_key(
    session: AsyncSession,
    *,
    user_id: str,
    key_name: str,
) -> str:
    api_key = _generate_api_key()
    session.add(
        APIKey(
            user_id=user_id,
            key_hash=hashlib.sha256(api_key.encode()).hexdigest(),
            key_mask=_mask_api_key(api_key),
            name=key_name,
            enabled_modules=["all"],
        )
    )
    return api_key


async def _run(args: argparse.Namespace) -> int:
    await _ensure_user_table()
    async with get_db_context() as session:
        user = await _find_or_create_user(
            session,
            email=str(args.email),
            name=str(args.name),
        )
        await _ensure_user_balance(
            session,
            user_id=user.id,
            tier=str(args.tier).strip() or _DEFAULT_USER_TIER,
        )
        key_name = await _resolve_key_name(
            session,
            user_id=user.id,
            requested_name=str(args.key_name),
        )
        api_key = await _create_api_key(
            session,
            user_id=user.id,
            key_name=key_name,
        )

    print(f"user_id={user.id}")
    print(f"email={user.email}")
    print(f"api_key_name={key_name}")
    print(f"api_key={api_key}")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
