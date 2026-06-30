def calculate_npm(net_profit, sales):
    if sales == 0:
        return None
    return round((net_profit / sales) * 100, 2)


def calculate_opm(operating_profit, sales):
    if sales == 0:
        return None
    return round((operating_profit / sales) * 100, 2)


def check_opm_difference(computed_opm, source_opm):
    if computed_opm is None or source_opm is None:
        return False

    return abs(computed_opm - source_opm) > 1


def calculate_roe(net_profit, equity_capital, reserves):
    equity = equity_capital + reserves

    if equity <= 0:
        return None

    return round((net_profit / equity) * 100, 2)


def calculate_roce(
    operating_profit,
    depreciation,
    equity_capital,
    reserves,
    borrowings
):
    capital_employed = (
        equity_capital +
        reserves +
        borrowings
    )

    if capital_employed <= 0:
        return None

    ebit = operating_profit - depreciation

    return round(
        (ebit / capital_employed) * 100,
        2
    )


def calculate_roa(net_profit, total_assets):
    if total_assets <= 0:
        return None

    return round(
        (net_profit / total_assets) * 100,
        2
    )