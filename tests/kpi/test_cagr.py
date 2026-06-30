from analytics.cagr import calculate_cagr


def test_normal_cagr():
    value, flag = calculate_cagr(100, 161.05, 5)

    assert round(value, 1) == 10.0
    assert flag == "NORMAL"


def test_turnaround():
    value, flag = calculate_cagr(-100, 200, 5)

    assert value is None
    assert flag == "TURNAROUND"


def test_decline_to_loss():
    value, flag = calculate_cagr(100, -50, 5)

    assert value is None
    assert flag == "DECLINE_TO_LOSS"


def test_both_negative():
    value, flag = calculate_cagr(-100, -50, 5)

    assert value is None
    assert flag == "BOTH_NEGATIVE"


def test_zero_base():
    value, flag = calculate_cagr(0, 100, 5)

    assert value is None
    assert flag == "ZERO_BASE"


def test_insufficient_years():
    value, flag = calculate_cagr(100, 200, 0)

    assert value is None
    assert flag == "INSUFFICIENT"


def test_positive_growth():
    value, flag = calculate_cagr(100, 200, 5)

    assert value > 0
    assert flag == "NORMAL"


def test_flat_growth():
    value, flag = calculate_cagr(100, 100, 5)

    assert value == 0.0
    assert flag == "NORMAL"


def test_large_growth():
    value, flag = calculate_cagr(100, 1000, 10)

    assert value > 0
    assert flag == "NORMAL"


def test_small_growth():
    value, flag = calculate_cagr(100, 110, 5)

    assert value > 0
    assert flag == "NORMAL"