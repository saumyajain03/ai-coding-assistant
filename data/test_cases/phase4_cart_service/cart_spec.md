# Cart Service Specification

## Overview
The `CartService` manages shopping cart items, calculates subtotals, applies promotional coupon discounts, and computes sales tax.

## Requirements

1. **Item Storage**:
   - Each item in the cart has: `item_id` (str), `name` (str), `price` (float), `quantity` (int).
   - `add_item(item_id, name, price, quantity=1)`: Adds item or increments quantity if item_id already exists.
   - `get_items()`: Returns list of cart items.

2. **Subtotal Calculation**:
   - `calculate_subtotal()`: Returns sum of `(price * quantity)` for all items in cart. Rounded to 2 decimal places.

3. **Promotional Coupons**:
   - `apply_coupon(code)`: Supports 2 valid coupon codes:
     * `"SAVE10"`: 10% off subtotal.
     * `"BULK20"`: 20% off subtotal, but ONLY valid if total item quantity across cart is 5 or more. If quantity < 5, raise `ValueError("BULK20 requires at least 5 total items")`.
     * Unknown coupon codes must raise `ValueError("Invalid coupon code")`.
   - Maximum discount cap: Any coupon discount cannot exceed `$50.00`. If calculated discount > 50.0, cap it at `50.0`.

4. **Tax and Final Total**:
   - Tax rate is fixed at `8.25%` (0.0825).
   - Tax is applied to `(subtotal - discount)`.
   - `checkout()` returns a dictionary:
     ```python
     {
         "subtotal": float,
         "discount": float,
         "taxable_amount": float,
         "tax": float,
         "total": float,
         "item_count": int,
     }
     ```
     All numeric values rounded to 2 decimal places.
