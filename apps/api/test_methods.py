import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv(".env")

import stripe

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

try:
    session = stripe.checkout.Session.create(
        payment_method_types=['card', 'alipay', 'wechat_pay', 'link'],
        payment_method_options={
            "wechat_pay": {
                "client": "web"
            }
        },
        line_items=[{
            'price_data': {
                'currency': 'cny',
                'product_data': {
                    'name': 'Test',
                },
                'unit_amount': 2000,
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url='https://example.com/success',
        cancel_url='https://example.com/cancel',
    )
    print("Session created successfully with card, alipay, wechat_pay, link")
    
    intent = stripe.PaymentIntent.create(
        amount=2000,
        currency='cny',
        payment_method_types=['card', 'alipay', 'wechat_pay', 'link'],
        payment_method_options={
            "wechat_pay": {
                "client": "web"
            }
        }
    )
    print("Intent created successfully with card, alipay, wechat_pay, link")
except Exception as e:
    print("Error:", e)
