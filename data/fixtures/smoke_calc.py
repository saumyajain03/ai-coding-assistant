"""
smoke_calc.py - Utility module for calculating discounted prices.
"""

from __future__ import annotations

__all__ = ["calculate_discount"]


def calculate_discount(price: float, discount: float) -> float:
    """Return the price after applying a discount."""
    if price < 0:
        raise ValueError("price must be non-negative")
    if not 0.0 <= discount <= 1.0:
        raise ValueError("discount must be between 0.0 and 1.0 inclusive")

    return price * (1.0 - discount)