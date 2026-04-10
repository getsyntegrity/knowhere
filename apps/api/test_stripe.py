import sys
import os
import asyncio

sys.path.append('.')
sys.path.append('../../')

import stripe
from shared.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

# try to create a dummy payment intent or retrieve available payment methods
def main():
    try:
        # One way is to just create a dummy checkout session without payment_method_types
        # and print the url
        print(settings.STRIPE_SECRET_KEY[:10] + "...")
        print("API initialized")
        
        # PaymentMethodConfigurations API can list supported methods if configured
    except Exception as e:
        print(e)

if __name__ == '__main__':
    main()
