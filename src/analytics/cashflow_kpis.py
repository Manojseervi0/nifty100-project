def calculate_fcf(
    operating_activity,
    investing_activity
):
    """
    Calculate Free Cash Flow.
    """
    return operating_activity + investing_activity


def calculate_cfo_quality_score(
    cfo,
    pat
):
    """
    Classify earnings quality using CFO/PAT ratio.
    """
    if pat == 0:
        return None

    ratio = cfo / pat

    if ratio > 1:
        return "High Quality"

    if ratio >= 0.5:
        return "Moderate"

    return "Accrual Risk"


def calculate_capex_intensity(
    investing_activity,
    sales
):
    """
    Classify CapEx intensity.
    """
    if sales == 0:
        return None

    intensity = (
        abs(investing_activity) / sales
    ) * 100

    if intensity < 3:
        return "Asset Light"

    if intensity <= 8:
        return "Moderate"

    return "Capital Intensive"


def calculate_fcf_conversion(
    fcf,
    operating_profit
):
    """
    Calculate FCF conversion rate.
    """
    if operating_profit == 0:
        return None

    return round(
        (fcf / operating_profit) * 100,
        2
    )


def classify_capital_allocation(
    cfo,
    cfi,
    cff,
    cfo_pat_ratio=None
):
    """
    Classify capital allocation pattern.
    """
    signs = (
        "+" if cfo >= 0 else "-",
        "+" if cfi >= 0 else "-",
        "+" if cff >= 0 else "-"
    )

    if signs == ("+", "-", "-"):
        if (
            cfo_pat_ratio is not None
            and cfo_pat_ratio > 1
        ):
            return "Shareholder Returns"
        return "Reinvestor"

    if signs == ("+", "+", "-"):
        return "Liquidating Assets"

    if signs == ("-", "+", "+"):
        return "Distress Signal"

    if signs == ("-", "-", "+"):
        return "Growth Funded by Debt"

    if signs == ("+", "+", "+"):
        return "Cash Accumulator"

    if signs == ("-", "-", "-"):
        return "Pre-Revenue"

    if signs == ("+", "-", "+"):
        return "Mixed"

    return "Other"