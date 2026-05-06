from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
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
from shared.utils.api_keys import generate_api_key, hash_api_key, mask_api_key

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
    parser.add_argument(
        "--api-key-output-file",
        default="",
        help="Optional file path for the generated API key. The file is created with 0600 permissions.",
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


def _write_api_key_file(path_value: str, api_key: str) -> Path:
    output_path = Path(path_value).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor = os.open(
        output_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as output_file:
        output_file.write(f"{api_key}\n")
    return output_path


async def _create_api_key(
    session: AsyncSession,
    *,
    user_id: str,
    key_name: str,
) -> str:
    api_key = generate_api_key()
    session.add(
        APIKey(
            user_id=user_id,
            key_hash=hash_api_key(api_key),
            key_mask=mask_api_key(api_key),
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
    print("credential_name_created=true")
    print("api_key_created=true")
    print("credential_hidden=true")
    output_path_value = str(args.api_key_output_file).strip()
    if output_path_value:
        output_path = _write_api_key_file(output_path_value, api_key)
        print(f"credential_output_file={output_path}")
    else:
        print("credential_output_file=")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
