"""
Test script to verify dynamic payment methods work correctly.
Creates checkout sessions with and without payment_method_types to compare.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv(".env")

import stripe

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

print("=" * 60)
print("Testing Dynamic Payment Methods")
print("=" * 60)

# Test 1: Checkout Session with dynamic payment methods (our new approach)
print("\n--- Test 1: Checkout Session (dynamic - no payment_method_types) ---")
try:
    session = stripe.checkout.Session.create(
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': 'Test Credits Package',
                },
                'unit_amount': 1000,  # $10.00
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url='https://example.com/success',
        cancel_url='https://example.com/cancel',
    )
    print(f"  Session ID: {session.id}")
    print(f"  Payment Method Types: {session.payment_method_types}")
    print(f"  URL: {session.url}")
    print(f"  Status: SUCCESS ✅")
except Exception as e:
    print(f"  Error: {e}")
    print(f"  Status: FAILED ❌")

# Test 2: Checkout Session for subscription mode (dynamic)
print("\n--- Test 2: Checkout Session subscription mode (dynamic) ---")
try:
    session_sub = stripe.checkout.Session.create(
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': 'Test Subscription',
                },
                'unit_amount': 1999,  # $19.99
                'recurring': {
                    'interval': 'month',
                },
            },
            'quantity': 1,
        }],
        mode='subscription',
        success_url='https://example.com/success',
        cancel_url='https://example.com/cancel',
    )
    print(f"  Session ID: {session_sub.id}")
    print(f"  Payment Method Types: {session_sub.payment_method_types}")
    print(f"  URL: {session_sub.url}")
    print(f"  Status: SUCCESS ✅")
except Exception as e:
    print(f"  Error: {e}")
    print(f"  Status: FAILED ❌")

# Test 3: PaymentIntent with automatic_payment_methods (our new approach)
print("\n--- Test 3: PaymentIntent (automatic_payment_methods) ---")
try:
    intent = stripe.PaymentIntent.create(
        amount=1000,
        currency='usd',
        automatic_payment_methods={"enabled": True},
        metadata={
            'user_id': 'test_user',
            'type': 'credits',
            'credits_amount': '10'
        }
    )
    print(f"  Intent ID: {intent.id}")
    print(f"  Payment Method Types: {intent.payment_method_types}")
    print(f"  Client Secret: {intent.client_secret[:30]}...")
    print(f"  Status: SUCCESS ✅")
except Exception as e:
    print(f"  Error: {e}")
    print(f"  Status: FAILED ❌")

# Test 4: Old approach for comparison (hardcoded)
print("\n--- Test 4: Checkout Session (old hardcoded ['card', 'alipay']) ---")
try:
    session_old = stripe.checkout.Session.create(
        payment_method_types=['card', 'alipay'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': 'Test Old Approach',
                },
                'unit_amount': 1000,
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url='https://example.com/success',
        cancel_url='https://example.com/cancel',
    )
    print(f"  Session ID: {session_old.id}")
    print(f"  Payment Method Types: {session_old.payment_method_types}")
    print(f"  URL: {session_old.url}")
    print(f"  Status: SUCCESS ✅")
except Exception as e:
    print(f"  Error: {e}")
    print(f"  Status: FAILED ❌")

print("\n" + "=" * 60)
print("Comparison: Dynamic should show MORE payment methods than hardcoded")
print("=" * 60)
