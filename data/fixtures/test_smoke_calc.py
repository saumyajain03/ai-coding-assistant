from smoke_calc import calculate_discount

def test_discount():
    assert calculate_discount(100.0, 0.2) == 80.0
