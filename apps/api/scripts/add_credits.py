import asyncio
import sys
import os

# Add parent directory to path to allow importing app modules
current_dir = os.path.dirname(os.path.abspath(__file__))
api_root = os.path.dirname(current_dir)
sys.path.append(api_root)

# Also add shared-python to path (assuming standard repo structure)
# github.com/ontosAI/knowhere-api/apps/api/scripts -> .../knowhere-api
repo_root = os.path.dirname(os.path.dirname(api_root))
shared_python_path = os.path.join(repo_root, "packages", "shared-python")
sys.path.append(shared_python_path)

from shared.services.billing import CreditsService
from shared.core.billing import MicroDollar

async def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/add_credits.py <email> <amount>")
        print("Example: python scripts/add_credits.py user@example.com 100")
        return

    email = sys.argv[1]
    amount = int(sys.argv[2])
    
    print(f"Connecting to database to add {amount} credits to {email}...")

    async with get_db_context() as db:
        user_repo = UserRepository()
        user = await user_repo.get_by_email(db, email)
        
        if not user:
            print(f"Error: User with email '{email}' not found.")
            return

        service = CreditsService()
        # Convert display credits (e.g., 100) to MicroDollar
        micro_amount = MicroDollar.from_dollars(amount)
        
        # Create a fake payment record to prevent check_balance from capping the credits
        # check_balance limits balance to the sum of recent payments in PaymentRecord
        from shared.models.database.payment_record import PaymentRecord
        from uuid import uuid4
        import datetime
        
        fake_payment_id = f"manual_grant_{uuid4()}"
        fake_payment = PaymentRecord(
            user_id=str(user.id),
            payment_intent_id=fake_payment_id,
            amount_cents=0,
            currency="USD",
            status="succeeded",
            credits_amount=micro_amount.amount, # Store int in DB
            payment_type="manual_grant",
            created_at=datetime.datetime.utcnow(),
            extra_metadata={"reason": "Manual dev top-up via script"}
        )
        db.add(fake_payment)
        await db.flush()
        
        success = await service.add_credits(
            session=db,
            user_id=str(user.id),
            amount=micro_amount.amount,
            reason="Manual dev top-up via script",
            transaction_type="manual_grant",
            stripe_payment_id=fake_payment_id
        )
        
        if success:
            await db.commit()
            print(f"Successfully added {amount} credits (value: {micro_amount}) to user {user.id}")
            
            # Fetch new balance to confirm
            new_balance = await service.get_balance(db, str(user.id))
            balance_display = MicroDollar(new_balance).to_credit()
            print(f"New Balance: {balance_display}")
        else:
            print("Failed to add credits.")

if __name__ == "__main__":
    asyncio.run(main())
