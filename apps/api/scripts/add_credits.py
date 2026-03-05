import asyncio
import datetime
import os
import sys
from typing import cast
from uuid import uuid4


def _bootstrap_python_path() -> None:
    """Allow running the script directly without preconfigured PYTHONPATH."""
    current_dir = os.path.dirname(os.path.abspath(__file__))  # apps/api/scripts
    api_root = os.path.dirname(current_dir)  # apps/api
    repo_root = os.path.dirname(os.path.dirname(api_root))  # repo root
    shared_python_path = os.path.join(repo_root, "packages", "shared-python")

    for path in (api_root, shared_python_path):
        if path not in sys.path:
            sys.path.insert(0, path)


_bootstrap_python_path()

from sqlalchemy import select
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.billing import MicroDollar
from shared.core.database import get_db_context
from shared.models.database.payment_record import PaymentRecord
from shared.models.database.user import User
from shared.models.database.webhook import WebhookEvent  # noqa: F401
from shared.services.billing import CreditsService


async def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python scripts/add_credits.py <email_or_user_id> <amount>")
        print("Example: python scripts/add_credits.py user@example.com 100")
        print("Example: python scripts/add_credits.py usr_abc123 100")
        return 1

    user_identifier = sys.argv[1].strip()
    try:
        amount = int(sys.argv[2])
    except ValueError:
        print(f"Error: amount must be an integer, got '{sys.argv[2]}'.")
        return 1

    if amount <= 0:
        print("Error: amount must be greater than 0.")
        return 1

    print(f"Connecting to database to add {amount} credits to {user_identifier}...")

    async with get_db_context() as db_session:
        db = cast(AsyncSession, db_session)
        result = await db.execute(
            select(User)
            .where(or_(User.email == user_identifier, User.id == user_identifier))
            .order_by(User.id.asc())
        )
        users = result.scalars().all()

        if not users:
            print(f"Error: user '{user_identifier}' not found (checked by email or user_id).")
            return 1
        if len(users) > 1:
            print(
                f"Warning: found {len(users)} users matching '{user_identifier}', "
                f"using first user id={users[0].id}."
            )

        user = users[0]
        service = CreditsService()
        micro_amount = MicroDollar.from_dollars(amount).amount

        # Record a succeeded manual payment so expiration checks include this grant.
        fake_payment_id = f"manual_grant_{uuid4()}"
        fake_payment = PaymentRecord(
            user_id=str(user.id),
            payment_intent_id=fake_payment_id,
            amount_cents=0,
            currency="USD",
            status="succeeded",
            credits_amount=micro_amount,
            payment_type="manual_grant",
            processed_at=datetime.datetime.utcnow(),
            extra_metadata={"reason": "Manual dev top-up via script"},
        )
        db.add(fake_payment)
        await db.flush()

        new_balance_micro = await service.add_credits(
            session=db,
            user_id=str(user.id),
            amount=micro_amount,
            reason="Manual dev top-up via script",
            transaction_type="manual_grant",
            stripe_payment_id=fake_payment_id,
        )

        print(
            f"Successfully added {amount} credits "
            f"(micro={micro_amount}) to user {user.id}"
        )
        print(f"New Balance: {MicroDollar(new_balance_micro).to_credit()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
