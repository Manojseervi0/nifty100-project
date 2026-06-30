from analytics.ratios import *

def test_npm():
    assert calculate_npm(100, 1000) == 10.0

def test_npm_zero_sales():
    assert calculate_npm(100, 0) is None

def test_opm():
    assert calculate_opm(200, 1000) == 20.0

def test_opm_mismatch():
    assert check_opm_difference(20, 17) is True

def test_roe():
    assert calculate_roe(100, 100, 400) == 20.0

def test_roe_negative_equity():
    assert calculate_roe(100, 50, -100) is None

def test_roce():
    assert calculate_roce(
        300,
        50,
        100,
        400,
        500
    ) == 25.0

def test_roa():
    assert calculate_roa(100, 1000) == 10.0