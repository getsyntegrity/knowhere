# Micro-Dollar Billing System Migration

**Date:** 2026-01-21  
**Author:** AI Assistant  
**PR Type:** Feature / Breaking Change

---

## Summary

Replaced the simplified "1 credit per page" billing with a high-precision **Micro-Dollar** system. This migration uses integer-based currency where **$1.00 = 1,000,000 micro-credits**, eliminating floating-point errors for low-unit-cost services like $0.0015/page.


## credits and micro-dollars
In our current system, we have 2 type of credits, 1 for display to user as an equivalent of dollars, and
1 for internal use as an equivalent of micro-dollars. So we may have in-consistency naming on same thing, or 
same name on different type

## Stripe Changes
There is 2 conversion when we tell stripe the amount of credits to buy
1: we need to convert micro dollar to credits
2: we need to convert credits to micro dollar

## Changes

### Phase 1: Core Module

| File | Change |
|------|--------|
| `micro_dollar.py` | Removed `from_db()`/`to_db()`, use constructor and `.amount` |
| `__init__.py` | Updated exports |
| `calculator.py` | Returns `MicroDollar` |

### Phase 2: Worker App

| File | Change |
|------|--------|
| `credits.py` | Uses `MicroDollar.amount` for repository calls |
| `kb_tasks.py` | Uses `MicroDollar.amount` for `job.credits_charged` |

### Phase 3: API Service Layer

| File | Change |
|------|--------|
| `credits_service.py` | All methods accept/return `MicroDollar` |
| `stripe_service.py` | Wraps amounts in `MicroDollar()` |
| `message_handlers.py` | Wraps refund amounts in `MicroDollar()` |

### Phase 4: API Routes

| File | Usages |
|------|--------|
| `auth.py` | 1 - `/me` endpoint |
| `oauth.py` | 3 - OAuth login responses |
| `billing.py` | 4 - balance, usage, price configs |
| `user_management.py` | 2 - balance, transactions |
| `users.py` | 1 - initial credits grant |

---

## Database Model Updates

**All credit columns store micro-credits (BigInteger):**

| Model | Column |
|-------|--------|
| `user.py` | `credits_balance` |
| `credits_transaction.py` | `credits_amount` |
| `job.py` | `credits_charged` |
| `stripe_price_config.py` | `credits_amount` |
| `payment_record.py` | `credits_amount` |

---

## Breaking Changes

> [!CAUTION]
> - `from_db()` and `to_db()` methods removed
> - Use `MicroDollar(value)` constructor and `.amount` property
> - All service methods now require `MicroDollar`, not int
> - Service methods return `MicroDollar`, not int

---

## Usage Examples

```python
from shared.core.billing import MicroDollar, BillingCalculator

# From database (in repository layer - raw int)
balance_int = await repository.get_balance(session, user_id)

# In service layer - convert to MicroDollar
balance = MicroDollar(balance_int)

# For API response
return {"credits_balance": balance.to_ui_string()}

# Calculate cost
calc = BillingCalculator()
cost = calc.calculate_page_cost(10)  # Returns MicroDollar

# Store to database (repository layer)
await repository.deduct_credits(session, user_id, cost.amount)

# Service layer call (MicroDollar in, MicroDollar out)
await credits_service.add_credits(session, user_id, cost, "description")
```

---

## Files Changed

### Modified Files
- `packages/shared-python/shared/core/billing/micro_dollar.py`
- `packages/shared-python/shared/core/billing/__init__.py`
- `apps/api/app/services/billing/credits_service.py` ⭐ Full MicroDollar I/O
- `apps/api/app/services/billing/stripe_service.py`
- `apps/api/app/services/messaging/message_handlers.py`
- `apps/api/app/api/v1/routes/auth.py`
- `apps/api/app/api/v1/routes/oauth.py`
- `apps/api/app/api/v1/routes/billing.py`
- `apps/api/app/api/v1/routes/user_management.py`
- `apps/api/app/core/users.py`
- `apps/worker/app/services/billing/credits.py`
- `apps/worker/app/core/tasks/kb_tasks.py`
