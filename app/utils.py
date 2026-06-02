from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from flask_login import current_user

CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}


def format_currency(value, currency=None):
    if value is None:
        return "-"
    try:
        v = float(value)
    except Exception:
        return str(value)
    if currency is None and current_user and current_user.is_authenticated:
        currency = current_user.preferred_currency or "INR"
    currency = currency or "INR"
    sym = CURRENCY_SYMBOLS.get(currency, "")
    if currency == "INR":
        # Indian grouping
        s = f"{v:,.2f}"
        # convert 1,234,567.89 -> 12,34,567.89
        if "." in s:
            int_part, dec = s.split(".")
        else:
            int_part, dec = s, "00"
        int_part = int_part.replace(",", "")
        neg = int_part.startswith("-")
        if neg:
            int_part = int_part[1:]
        if len(int_part) > 3:
            last3 = int_part[-3:]
            rest = int_part[:-3]
            rest_grouped = ",".join([rest[max(i - 2, 0):i] for i in range(len(rest), 0, -2)][::-1])
            int_part = rest_grouped + "," + last3
        return f"{sym} {'-' if neg else ''}{int_part}.{dec}"
    return f"{sym} {v:,.2f}"


def format_date(d, fmt=None):
    if not d:
        return "-"
    if fmt is None and current_user and current_user.is_authenticated:
        fmt = current_user.preferred_date_format or "%d %b %Y"
    fmt = fmt or "%d %b %Y"
    try:
        return d.strftime(fmt)
    except Exception:
        return str(d)


# ─────────────────────────────────────────────────────────────────────
# Amortization engine
# ─────────────────────────────────────────────────────────────────────

def emi_amount(principal: float, annual_rate: float, months: int) -> float:
    """Standard EMI formula. annual_rate in %, e.g. 8.5"""
    if months <= 0:
        return 0.0
    r = (annual_rate / 100.0) / 12.0
    if r == 0:
        return round(principal / months, 2)
    emi = principal * r * (1 + r) ** months / ((1 + r) ** months - 1)
    return round(emi, 2)


def generate_amortization(loan):
    """Build a list of dicts representing the schedule rows.
    Handles balloon: if balloon_date/amount set, the installment dated
    on/just after balloon_date absorbs the remaining principal+interest
    and closes the schedule there.
    """
    rows = []
    principal_outstanding = float(loan.loan_amount) - float(loan.down_payment or 0)
    annual_rate = float(loan.interest_rate)
    months = int(loan.tenure_months)
    monthly_rate = (annual_rate / 100.0) / 12.0
    emi = emi_amount(principal_outstanding, annual_rate, months)

    bal_date = loan.balloon_date
    for i in range(1, months + 1):
        pay_date = loan.start_date + relativedelta(months=i)
        interest = round(principal_outstanding * monthly_rate, 2)
        principal_component = round(emi - interest, 2)
        is_balloon = False

        if bal_date and pay_date >= bal_date:
            # close out as balloon
            principal_component = round(principal_outstanding, 2)
            emi_row = round(principal_component + interest, 2)
            principal_outstanding = 0.0
            rows.append({
                "month_index": i,
                "payment_date": pay_date,
                "emi": emi_row,
                "principal": principal_component,
                "interest": interest,
                "remaining_balance": 0.0,
                "is_balloon": True,
            })
            break

        if i == months:
            # adjust last installment to clear any rounding
            principal_component = round(principal_outstanding, 2)
            emi_row = round(principal_component + interest, 2)
            principal_outstanding = 0.0
            rows.append({
                "month_index": i,
                "payment_date": pay_date,
                "emi": emi_row,
                "principal": principal_component,
                "interest": interest,
                "remaining_balance": 0.0,
                "is_balloon": False,
            })
            break

        principal_outstanding = round(principal_outstanding - principal_component, 2)
        rows.append({
            "month_index": i,
            "payment_date": pay_date,
            "emi": emi,
            "principal": principal_component,
            "interest": interest,
            "remaining_balance": max(principal_outstanding, 0.0),
            "is_balloon": False,
        })
    return rows


def recalc_unpaid_with_new_rate(loan, new_rate: float, effective_date: date):
    """Rebuild only unpaid installments with new_rate from effective_date.
    Paid installments are immutable.
    """
    from app.models import Schedule
    paid = [s for s in loan.schedules if s.payment_status == "Paid"]
    unpaid = [s for s in loan.schedules if s.payment_status != "Paid"]
    if not unpaid:
        return 0
    # remaining principal = balance after last paid
    if paid:
        last_paid = max(paid, key=lambda s: s.month_index)
        remaining_principal = last_paid.remaining_balance
        start_index = last_paid.month_index
        start_date = last_paid.payment_date
    else:
        remaining_principal = float(loan.loan_amount) - float(loan.down_payment or 0)
        start_index = 0
        start_date = loan.start_date

    months_left = len(unpaid)
    monthly_rate = (new_rate / 100.0) / 12.0
    new_emi = emi_amount(remaining_principal, new_rate, months_left)

    for n, s in enumerate(sorted(unpaid, key=lambda x: x.month_index), start=1):
        interest = round(remaining_principal * monthly_rate, 2)
        principal_component = round(new_emi - interest, 2)
        if n == months_left:
            principal_component = round(remaining_principal, 2)
            s.emi = round(principal_component + interest, 2)
        else:
            s.emi = new_emi
        s.interest = interest
        s.principal = principal_component
        remaining_principal = round(remaining_principal - principal_component, 2)
        s.remaining_balance = max(remaining_principal, 0.0)
        s.is_revised = True
    return months_left


def recalc_with_lumpsum(loan, lumpsum: float):
    """Apply a lump-sum prepayment against the next unpaid installment's
    remaining balance, then re-amortize remaining installments at current rate
    keeping tenure the same number of months.
    """
    unpaid = sorted([s for s in loan.schedules if s.payment_status != "Paid"], key=lambda x: x.month_index)
    if not unpaid:
        return 0
    paid = [s for s in loan.schedules if s.payment_status == "Paid"]
    if paid:
        last_paid = max(paid, key=lambda s: s.month_index)
        remaining = last_paid.remaining_balance
    else:
        remaining = float(loan.loan_amount) - float(loan.down_payment or 0)
    remaining = max(remaining - lumpsum, 0.0)
    months_left = len(unpaid)
    monthly_rate = (float(loan.interest_rate) / 100.0) / 12.0
    new_emi = emi_amount(remaining, float(loan.interest_rate), months_left)
    for n, s in enumerate(unpaid, start=1):
        interest = round(remaining * monthly_rate, 2)
        principal_component = round(new_emi - interest, 2)
        if n == months_left:
            principal_component = round(remaining, 2)
            s.emi = round(principal_component + interest, 2)
        else:
            s.emi = new_emi
        s.interest = interest
        s.principal = principal_component
        remaining = max(round(remaining - principal_component, 2), 0.0)
        s.remaining_balance = remaining
        s.is_revised = True
    return months_left


def update_loan_progress(loan):
    """Recompute remaining_balance, completion %, and loan_status from schedule."""
    schedules = list(loan.schedules)
    if not schedules:
        return
    total_emi = sum(s.emi for s in schedules)
    paid_total = sum(s.emi for s in schedules if s.payment_status == "Paid")
    loan.completion_percentage = round((paid_total / total_emi) * 100, 2) if total_emi else 0
    unpaid = [s for s in schedules if s.payment_status != "Paid"]
    if unpaid:
        next_un = min(unpaid, key=lambda s: s.month_index)
        # remaining balance = balance carried into next unpaid (which equals balance after the previous paid)
        prev = [s for s in schedules if s.month_index < next_un.month_index]
        loan.remaining_balance = prev[-1].remaining_balance if prev else (loan.loan_amount - (loan.down_payment or 0))
    else:
        loan.remaining_balance = 0
    overdue = any(s.payment_status != "Paid" and s.payment_date < date.today() for s in schedules)
    if loan.remaining_balance <= 0.01 and not unpaid:
        loan.loan_status = "Completed"
        from datetime import datetime
        if not loan.closed_at:
            loan.closed_at = datetime.utcnow()
            loan.final_amount = sum(s.emi for s in schedules)
    elif loan.balloon_date and any(s.is_balloon and s.payment_status != "Paid" for s in schedules):
        loan.loan_status = "Balloon Pending"
    elif overdue:
        loan.loan_status = "Overdue"
    else:
        loan.loan_status = "Active"


def portfolio_health_score(loans):
    """0-100 score from completion %, payment consistency, overdue exposure, balloon exposure."""
    if not loans:
        return 100
    total_completion = sum(l.completion_percentage for l in loans) / len(loans)
    overdue_count = sum(1 for l in loans if l.loan_status == "Overdue")
    balloon_count = sum(1 for l in loans if l.loan_status == "Balloon Pending")
    paid_consistency = 0
    total_due_now = 0
    paid_on_time = 0
    today = date.today()
    for l in loans:
        for s in l.schedules:
            if s.payment_date <= today:
                total_due_now += 1
                if s.payment_status == "Paid":
                    paid_on_time += 1
    consistency = (paid_on_time / total_due_now) if total_due_now else 1
    score = (
        0.40 * total_completion
        + 0.35 * consistency * 100
        + 0.15 * max(0, 100 - overdue_count * 15)
        + 0.10 * max(0, 100 - balloon_count * 10)
    )
    return round(min(max(score, 0), 100))
