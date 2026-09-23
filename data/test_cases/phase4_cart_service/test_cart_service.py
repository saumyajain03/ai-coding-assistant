import pytest
from cart_service import CartService


def test_add_items_and_subtotal():
    cart = CartService()
    cart.add_item("item-1", "Mechanical Keyboard", 100.0, 1)
    cart.add_item("item-2", "Wireless Mouse", 50.0, 2)
    assert cart.calculate_subtotal() == 200.0


def test_coupon_save10():
    cart = CartService()
    cart.add_item("item-1", "Monitor", 200.0, 1)
    cart.apply_coupon("SAVE10")
    summary = cart.checkout()
    assert summary["subtotal"] == 200.0
    assert summary["discount"] == 20.0
    assert summary["taxable_amount"] == 180.0
    # Tax: 180 * 0.0825 = 14.85
    assert summary["tax"] == 14.85
    assert summary["total"] == 194.85


def test_coupon_bulk20_valid():
    cart = CartService()
    # 5 items total -> eligible for BULK20
    cart.add_item("item-1", "USB Cable", 20.0, 5)
    cart.apply_coupon("BULK20")
    summary = cart.checkout()
    assert summary["subtotal"] == 100.0
    assert summary["discount"] == 20.0
    assert summary["taxable_amount"] == 80.0
    # Tax: 80 * 0.0825 = 6.6
    assert summary["tax"] == 6.6
    assert summary["total"] == 86.6


def test_coupon_bulk20_insufficient_quantity():
    cart = CartService()
    cart.add_item("item-1", "USB Cable", 20.0, 4)
    with pytest.raises(ValueError, match="BULK20 requires at least 5 total items"):
        cart.apply_coupon("BULK20")


def test_coupon_max_discount_cap_50():
    cart = CartService()
    # Subtotal $800 with SAVE10 would be $80 discount, but cap is $50
    cart.add_item("item-1", "Laptop", 800.0, 1)
    cart.apply_coupon("SAVE10")
    summary = cart.checkout()
    assert summary["discount"] == 50.0
    assert summary["taxable_amount"] == 750.0
