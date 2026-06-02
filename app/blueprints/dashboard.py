from datetime import date, timedelta
from collections import defaultdict
from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from dateutil.relativedelta import relativedelta
from app.models import Loan
from app.utils import portfolio_health_score

dashboard_bp = Blueprint("dashboard", __name__)


def _stats(loans):
    today = date.today()
    month_start = today.replace(day=1)
    total_loan_amount = sum(l.loan_amount for l in loans)
    total_paid = 0
    total_interest = 0
    outstanding = 0
    for l in loans:
        for s in l.schedules:
            total_interest += s.interest
            if s.payment_status == "Paid":
                total_paid += s.emi
            else:
                outstanding += s.emi
    active = sum(1 for l in loans if l.loan_status in ("Active", "Balloon Pending"))
    completed = sum(1 for l in loans if l.loan_status == "Completed")
    closed_this_month = sum(1 for l in loans if l.closed_at and l.closed_at.date() >= month_start)
    remaining = sum(l.remaining_balance for l in loans)
    return {
        "total_loan_amount": total_loan_amount,
        "total_interest": total_interest,
        "active": active,
        "completed": completed,
        "closed_this_month": closed_this_month,
        "remaining": remaining,
        "total_paid": total_paid,
        "outstanding": outstanding,
        "health": portfolio_health_score(loans),
    }


def _charts(loans):
    # distribution by bank, category, status
    by_bank = defaultdict(float)
    by_cat = defaultdict(float)
    by_status = defaultdict(int)
    for l in loans:
        by_bank[l.bank_name] += l.remaining_balance or l.loan_amount
        by_cat[l.loan_category] += l.remaining_balance or l.loan_amount
        by_status[l.loan_status] += 1

    today = date.today()
    # Cash flow projection for 12 months
    cashflow = []
    for m in range(0, 12):
        d = (today.replace(day=1) + relativedelta(months=m))
        nxt = d + relativedelta(months=1)
        amt = 0
        for l in loans:
            for s in l.schedules:
                if d <= s.payment_date < nxt and s.payment_status != "Paid":
                    amt += s.emi
        cashflow.append({"month": d.strftime("%b %Y"), "amount": round(amt, 2)})

    # Debt reduction trend (next 12 months projected remaining)
    debt_trend = []
    for m in range(0, 12):
        d = today.replace(day=1) + relativedelta(months=m)
        nxt = d + relativedelta(months=1)
        remaining = 0
        for l in loans:
            future = [s for s in l.schedules if s.payment_date >= nxt and s.payment_status != "Paid"]
            if future:
                remaining += min(s.remaining_balance for s in future) if False else future[0].remaining_balance
        debt_trend.append({"month": d.strftime("%b %Y"), "remaining": round(remaining, 2)})

    # Interest burden
    principal_remaining = 0
    interest_remaining = 0
    interest_saved = 0
    for l in loans:
        for s in l.schedules:
            if s.payment_status != "Paid":
                principal_remaining += s.principal
                interest_remaining += s.interest
            if s.is_revised:
                interest_saved += max(s.interest * 0.05, 0)  # heuristic

    # Balloon risk
    balloon = []
    for l in loans:
        for s in l.schedules:
            if s.is_balloon and s.payment_status != "Paid":
                days = (s.payment_date - today).days
                risk = "High" if days < 30 else ("Medium" if days < 90 else "Low")
                balloon.append({
                    "loan_id": l.loan_id, "loan_name": l.loan_name,
                    "due": s.payment_date.isoformat(), "days": days,
                    "amount": s.emi, "risk": risk,
                })

    # Completion forecast
    forecast = []
    for l in loans:
        if l.loan_status in ("Completed", "Archived"):
            continue
        unpaid = [s for s in l.schedules if s.payment_status != "Paid"]
        if unpaid:
            last = max(unpaid, key=lambda s: s.month_index)
            forecast.append({"loan": f"{l.loan_id} · {l.loan_name}", "closes": last.payment_date.isoformat()})

    # Smart insights
    insights = []
    for l in loans:
        if l.completion_percentage >= 60:
            insights.append(f"{l.completion_percentage:.0f}% repaid on {l.loan_id}")
        if l.balloon_date:
            d = (l.balloon_date - today).days
            if 0 <= d <= 60:
                insights.append(f"Balloon for {l.loan_id} due in {d} days")
    if not insights:
        insights.append("Portfolio healthy — no urgent actions")

    return {
        "by_bank": dict(by_bank),
        "by_cat": dict(by_cat),
        "by_status": dict(by_status),
        "cashflow": cashflow,
        "debt_trend": debt_trend,
        "interest_burden": {
            "principal_remaining": round(principal_remaining, 2),
            "interest_remaining": round(interest_remaining, 2),
            "interest_saved": round(interest_saved, 2),
        },
        "balloon": balloon,
        "forecast": forecast,
        "insights": insights[:6],
    }


@dashboard_bp.route("/dashboard")
@login_required
def index():
    loans = current_user.loans.filter_by(is_archived=False).all()
    stats = _stats(loans)
    charts = _charts(loans)
    return render_template("dashboard/index.html", stats=stats, charts=charts, loans=loans)


@dashboard_bp.route("/api/dashboard/stats")
@login_required
def stats_api():
    loans = current_user.loans.filter_by(is_archived=False).all()
    return jsonify({"stats": _stats(loans), "charts": _charts(loans)})
