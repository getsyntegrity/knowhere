"""
Billing services for the worker.
"""
from .credits import deduct_credits

__all__ = ["deduct_credits"]
