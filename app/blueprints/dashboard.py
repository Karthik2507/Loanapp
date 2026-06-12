from datetime import date, timedelta, datetime
from collections import defaultdict
from flask import Blueprint, render_template, jsonify, url_for
from flask_login import login_required, current_user
from dateutil.relativedelta import relativedelta
from app.models import Loan, Setting
from app.utils import portfolio_health_score, emi_amount, format_currency

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
    active = sum(1 for l in loans if l.loan_status != "Completed")
    completed = sum(1 for l in loans if l.loan_status == "Completed")
    closed_this_month = sum(1 for l in loans if l.closed_at and l.closed_at.date() >= month_start)
    remaining = sum(l.remaining_balance for l in loans)

    # Weighted Average Interest Rate
    active_loans = [l for l in loans if l.loan_status != "Completed"]
    total_remaining_active = sum(l.remaining_balance for l in active_loans)
    if total_remaining_active > 0:
        weighted_interest_rate = sum(l.interest_rate * l.remaining_balance for l in active_loans) / total_remaining_active
    else:
        weighted_interest_rate = sum(l.interest_rate for l in active_loans) / len(active_loans) if active_loans else 0.0

    # Monthly Income and DTI Ratio
    income_rec = Setting.query.filter_by(user_id=current_user.id, key="monthly_income").first()
    monthly_income = float(income_rec.value) if income_rec and income_rec.value else 0.0
    
    total_monthly_emi = 0.0
    for l in active_loans:
        if l.custom_emi:
            total_monthly_emi += float(l.custom_emi)
        else:
            principal = float(l.loan_amount) - float(l.down_payment or 0)
            total_monthly_emi += emi_amount(principal, l.interest_rate, l.tenure_months)

    dti_ratio = (total_monthly_emi / monthly_income) * 100 if monthly_income > 0 else 0.0

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
        "weighted_interest_rate": round(weighted_interest_rate, 2),
        "monthly_income": round(monthly_income, 2),
        "total_monthly_emi": round(total_monthly_emi, 2),
        "dti_ratio": round(dti_ratio, 2)
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
    active_loans = [l for l in loans if l.loan_status != "Completed"]
    
    # Refinancing alerts for high rates
    for l in active_loans:
        if l.interest_rate > 9.0:
            insights.append(f"Refinance alert: {l.loan_id} rate is {l.interest_rate:.1f}%. Consider refinancing to save interest.")
            
    # Prepayment calculation tip
    if active_loans:
        # Find active loan with highest remaining balance
        target_loan = max(active_loans, key=lambda l: l.remaining_balance)
        if target_loan.remaining_balance > 5000:
            unpaid_count = sum(1 for s in target_loan.schedules if s.payment_status != "Paid")
            if unpaid_count > 6:
                std_emi = target_loan.custom_emi if target_loan.custom_emi else emi_amount(
                    float(target_loan.loan_amount) - float(target_loan.down_payment or 0),
                    target_loan.interest_rate,
                    target_loan.tenure_months
                )
                extra = round(std_emi * 0.1, -1)
                if extra >= 50:
                    monthly_rate = (target_loan.interest_rate / 100.0) / 12.0
                    rem_extra = target_loan.remaining_balance
                    months_with_extra = 0
                    total_interest_extra = 0.0
                    total_interest_normal = sum(s.interest for s in target_loan.schedules if s.payment_status != "Paid")
                    
                    for m in range(1, unpaid_count + 1):
                        interest = max(round(rem_extra * monthly_rate, 2), 0.0)
                        principal_comp = round((std_emi - interest) + extra, 2)
                        if principal_comp >= rem_extra:
                            total_interest_extra += interest
                            months_with_extra = m
                            break
                        total_interest_extra += interest
                        rem_extra = round(rem_extra - principal_comp, 2)
                        months_with_extra = m
                        
                    saved_months = unpaid_count - months_with_extra
                    saved_interest = max(total_interest_normal - total_interest_extra, 0.0)
                    if saved_months > 0 and saved_interest > 100:
                        from app.utils import format_currency
                        formatted_extra = format_currency(extra, current_user.preferred_currency)
                        formatted_saved = format_currency(saved_interest, current_user.preferred_currency)
                        insights.append(f"Prepay tip: Adding {formatted_extra}/mo on {target_loan.loan_id} saves {formatted_saved} and cuts tenure by {saved_months} months.")

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


@dashboard_bp.route("/api/notifications")
@login_required
def notifications_api():
    from app.models import Schedule, ActivityLog
    
    today = date.today()
    forty_five_days_later = today + timedelta(days=45)
    
    notifications = []
    
    # Fetch all active (non-completed, non-archived) loans
    active_loans = current_user.loans.filter(
        Loan.loan_status != "Completed",
        Loan.is_archived == False
    ).all()
    
    # 1. Overdue Installments
    for loan in active_loans:
        overdue_schedules = loan.schedules.filter(
            Schedule.payment_date < today,
            Schedule.payment_status != "Paid"
        ).all()
        
        for s in overdue_schedules:
            notifications.append({
                "id": f"overdue-{s.id}",
                "type": "overdue",
                "title": "Overdue Payment",
                "message": f"EMI of {format_currency(s.emi, current_user.preferred_currency)} for '{loan.loan_name}' (ID: {loan.loan_id}) was due on {s.payment_date.strftime('%d %b %Y')}.",
                "date": s.payment_date.isoformat(),
                "severity": "high",
                "link": url_for("schedule.view", loan_pk=loan.id)
            })
            
    # 2. Impending Balloon Payments (within 45 days)
    for loan in active_loans:
        balloon_schedules = loan.schedules.filter(
            Schedule.is_balloon == True,
            Schedule.payment_status != "Paid",
            Schedule.payment_date >= today,
            Schedule.payment_date <= forty_five_days_later
        ).all()
        
        for s in balloon_schedules:
            days = (s.payment_date - today).days
            notifications.append({
                "id": f"balloon-{s.id}",
                "type": "balloon",
                "title": "Impending Balloon Payment",
                "message": f"Balloon payment of {format_currency(s.emi, current_user.preferred_currency)} for '{loan.loan_name}' is due in {days} days ({s.payment_date.strftime('%d %b %Y')}).",
                "date": s.payment_date.isoformat(),
                "severity": "high" if days <= 15 else "medium",
                "link": url_for("schedule.view", loan_pk=loan.id)
            })
            
    # 3. Successful Bulk Imports / Updates (ActivityLog entries in the last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    bulk_activities = ActivityLog.query.filter(
        ActivityLog.user_id == current_user.id,
        ActivityLog.created_at >= seven_days_ago,
        ActivityLog.detail.like("%Bulk load%")
    ).order_by(ActivityLog.created_at.desc()).all()
    
    for act in bulk_activities:
        title = "Bulk Import Success" if act.action == "CREATE_LOAN" else "Bulk Update Success"
        message = act.detail
        loan = Loan.query.get(act.loan_id) if act.loan_id else None
        
        if act.action == "EDIT_LOAN" and loan:
            message = f"Loan '{loan.loan_name}' (ID: {loan.loan_id}) updated via bulk upload."
        elif act.action == "CREATE_LOAN":
            clean_detail = act.detail.replace("(Bulk load)", "").strip()
            message = f"Loan '{clean_detail}' created via bulk upload."
            
        notifications.append({
            "id": f"activity-{act.id}",
            "type": "import",
            "title": title,
            "message": message,
            "date": act.created_at.isoformat() + "Z", # Mark as UTC
            "severity": "info",
            "link": url_for("loans.details", loan_pk=loan.id) if loan else None
        })
        
    # Sort notifications by severity and date
    severity_order = {"high": 0, "medium": 1, "info": 2}
    notifications.sort(key=lambda x: (severity_order.get(x["severity"], 3), x["date"]))
    
    return jsonify({"notifications": notifications})
