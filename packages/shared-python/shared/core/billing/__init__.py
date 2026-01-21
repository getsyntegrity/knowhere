"""
Core billing module for high-precision micro-dollar billing.

$1.00 = 1,000,000 micro-credits (micros)

Usage:
    from shared.core.billing import MicroDollar, BillingCalculator
    
    # Create from int value
    balance = MicroDollar(user.credits_balance)
    
    # Calculate cost
    calc = BillingCalculator()
    cost = calc.calculate_page_cost(10)  # Returns MicroDollar
    
    # Get raw int value
    job.credits_charged = cost.amount
    
    # To frontend display (1M micros = 1 display credit)
    display_credits = balance.to_ui_string()
"""
from .micro_dollar import MicroDollar
from .calculator import BillingCalculator

__all__ = [
    "MicroDollar", 
    "BillingCalculator",
]
