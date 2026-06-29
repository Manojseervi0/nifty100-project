import csv


def log_failure(rule_id, table_name, record_id, severity, message):
    with open(
        "output/validation_failures.csv",
        "a",
        newline="",
        encoding="utf-8"
    ) as f:
        writer = csv.writer(f)
        writer.writerow([
            rule_id,
            table_name,
            record_id,
            severity,
            message
        ])


def dq01_company_pk_uniqueness(df):
    total_rows = len(df)
    unique_ids = df["id"].nunique()

    if total_rows == unique_ids:
        print("DQ-01 PASSED")
        return True

    print("DQ-01 FAILED")

    log_failure(
        "DQ-01",
        "companies",
        "ALL",
        "CRITICAL",
        "Duplicate company IDs found"
    )

    return False

def dq02_annual_pk_uniqueness(df, table_name):
    duplicates = df.duplicated(
        subset=["company_id", "year"],
        keep=False
    )

    dup_rows = df[duplicates]

    if dup_rows.empty:
        print(f"DQ-02 PASSED: {table_name}")
        return True

    print(f"DQ-02 FAILED: {table_name}")

    for _, row in dup_rows.iterrows():
        log_failure(
            "DQ-02",
            table_name,
            f"{row['company_id']}_{row['year']}",
            "CRITICAL",
            "Duplicate (company_id, year) found"
        )

    return False