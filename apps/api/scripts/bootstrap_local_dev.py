from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.local_dev_bootstrap_service import LocalDevelopmentBootstrapService
from shared.core.database import get_db_context


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bootstrap local-only database state for Knowhere API development.",
    )
    parser.add_argument(
        "--mode",
        choices=("ensure-user-table", "seed", "print-profile"),
        required=True,
        help="Bootstrap mode to run.",
    )
    return parser


async def _run(mode: str) -> int:
    service = LocalDevelopmentBootstrapService()

    if mode == "print-profile":
        _print_profile()
        return 0

    if mode == "ensure-user-table":
        await service.ensure_user_table_exists()
        print('Ensured local development table: "user"')
        return 0

    async with get_db_context() as session:
        await service.seed_local_developer(session)

    print("Ensured local development developer account.")
    _print_profile()
    return 0


def _print_profile() -> None:
    profile = LocalDevelopmentBootstrapService.get_local_developer_profile()
    print(f"user_id={profile['user_id']}")
    print(f"name={profile['name']}")
    print(f"email={profile['email']}")
    print(f"tier={profile['tier']}")
    print(f"api_key={profile['api_key']}")


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args.mode))


if __name__ == "__main__":
    raise SystemExit(main())
