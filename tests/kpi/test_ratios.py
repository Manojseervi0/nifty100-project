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

def test_debt_to_equity():
    assert calculate_debt_to_equity(500, 100, 400) == 1.0

def test_debt_free():
    assert calculate_debt_to_equity(0, 100, 400) == 0

def test_high_leverage_flag():
    assert high_leverage_flag(6, "Industrials") is True

def test_high_leverage_financials():
    assert high_leverage_flag(6, "Financials") is False

def test_icr():
    assert calculate_interest_coverage(200, 50, 50) == 5.0

def test_icr_debt_free():
    assert calculate_interest_coverage(200, 50, 0) is None

def test_icr_warning():
    assert icr_warning_flag(1.2) is True

def test_asset_turnover():
    assert calculate_asset_turnover(1000, 500) == 2.0