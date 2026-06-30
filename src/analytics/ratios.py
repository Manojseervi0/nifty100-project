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

def calculate_debt_to_equity(
    borrowings,
    equity_capital,
    reserves
):
    if borrowings == 0:
        return 0

    equity = equity_capital + reserves

    if equity <= 0:
        return None

    return round(borrowings / equity, 2)


def high_leverage_flag(
    debt_to_equity,
    broad_sector
):
    return (
        debt_to_equity is not None
        and debt_to_equity > 5
        and broad_sector != "Financials"
    )


def calculate_interest_coverage(
    operating_profit,
    other_income,
    interest
):
    if interest == 0:
        return None

    return round(
        (operating_profit + other_income)
        / interest,
        2
    )


def icr_label(icr):
    if icr is None:
        return "Debt Free"
    return None


def icr_warning_flag(icr):
    return icr is not None and icr < 1.5


def calculate_net_debt(
    borrowings,
    investments
):
    return borrowings - investments


def calculate_asset_turnover(
    sales,
    total_assets
):
    if total_assets == 0:
        return None

    return round(
        sales / total_assets,
        2
    )