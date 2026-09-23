"""
Cart Service Implementation (Stub / Buggy baseline).
Needs completion based on cart_spec.md and test_cart_service.py.
"""
from typing import Dict, List, Any


class CartService:
    def __init__(self):
        self.items: Dict[str, Dict[str, Any]] = {}
        self.active_coupon: str = None

    def add_item(self, item_id: str, name: str, price: float, quantity: int = 1) -> None:
        if item_id in self.items:
            self.items[item_id]["quantity"] += quantity
        else:
            self.items[item_id] = {
                "item_id": item_id,
                "name": name,
                "price": float(price),
                "quantity": int(quantity),
            }

    def get_items(self) -> List[Dict[str, Any]]:
        return list(self.items.values())

    def calculate_subtotal(self) -> float:
        total = sum(item["price"] * item["quantity"] for item in self.items.values())
        return round(total, 2)

    def apply_coupon(self, code: str) -> None:
        # TODO: Implement coupon validation (SAVE10, BULK20) and constraints
        raise NotImplementedError("apply_coupon not implemented")

    def checkout(self) -> Dict[str, Any]:
        # BUGGY / INCOMPLETE: Does not apply discount or calculate tax
        subtotal = self.calculate_subtotal()
        return {
            "subtotal": subtotal,
            "discount": 0.0,
            "taxable_amount": subtotal,
            "tax": 0.0,
            "total": subtotal,
            "item_count": sum(item["quantity"] for item in self.items.values()),
        }
