from analytics.cashflow_kpis import *


def test_fcf_positive():
    assert calculate_fcf(1000, -300) == 700


def test_fcf_negative():
    assert calculate_fcf(500, -800) == -300


def test_cfo_quality_high():
    assert calculate_cfo_quality_score(120, 100) == "High Quality"


def test_cfo_quality_moderate():
    assert calculate_cfo_quality_score(70, 100) == "Moderate"


def test_cfo_quality_risk():
    assert calculate_cfo_quality_score(30, 100) == "Accrual Risk"


def test_capex_asset_light():
    assert calculate_capex_intensity(-20, 1000) == "Asset Light"


def test_capex_moderate():
    assert calculate_capex_intensity(-50, 1000) == "Moderate"


def test_capex_intensive():
    assert calculate_capex_intensity(-120, 1000) == "Capital Intensive"


def test_fcf_conversion():
    assert calculate_fcf_conversion(500, 1000) == 50.0


def test_capital_allocation():
    assert classify_capital_allocation(
        100,
        -50,
        -20
    ) == "Reinvestor"