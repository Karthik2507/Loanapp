from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import Loan, RecalculationHistory, ActivityLog
from app.forms import RecalcForm
from app.utils import recalc_unpaid_with_new_rate, recalc_with_lumpsum, emi_amount, update_loan_progress

recalc_bp = Blueprint("recalc", __name__, url_prefix="/recalculate")


def _get_loan(loan_pk):
    loan = Loan.query.filter_by(id=loan_pk, user_id=current_user.id).first()
    if not loan:
        abort(404)
    return loan


@recalc_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    loans = current_user.loans.filter_by(is_archived=False).all()
    selected_id = request.args.get("loan_pk", type=int)
    loan = _get_loan(selected_id) if selected_id else (loans[0] if loans else None)
    form = RecalcForm()
    simulation = None
    if loan and form.validate_on_submit():
        rtype = form.recalc_type.data
        summary = ""
        if rtype == "RATE" and form.new_rate.data is not None:
            from datetime import date
            recalc_unpaid_with_new_rate(loan, form.new_rate.data, form.effective_date.data or date.today())
            loan.interest_rate = form.new_rate.data
            summary = f"Rate changed to {form.new_rate.data}%"
        elif rtype == "TENURE" and form.new_tenure.data:
            # rebuild unpaid stretched/compressed to new tenure
            unpaid = sorted([s for s in loan.schedules if s.payment_status != "Paid"], key=lambda x: x.month_index)
            if unpaid:
                remaining = unpaid[0].remaining_balance + unpaid[0].principal  # principal before this installment
                # simpler: recalc using current remaining_balance of loan
                remaining = loan.remaining_balance
                monthly_rate = (loan.interest_rate / 100.0) / 12.0
                new_emi = emi_amount(remaining, loan.interest_rate, form.new_tenure.data)
                # Truncate or extend schedule rows in-place (recreate)
                # delete existing unpaid rows
                from app.models import Schedule
                from dateutil.relativedelta import relativedelta
                start_date = unpaid[0].payment_date
                start_idx = unpaid[0].month_index - 1
                for s in unpaid:
                    db.session.delete(s)
                db.session.flush()
                rem = remaining
                for i in range(1, form.new_tenure.data + 1):
                    interest = round(rem * monthly_rate, 2)
                    principal = round(new_emi - interest, 2)
                    if i == form.new_tenure.data:
                        principal = round(rem, 2)
                        emi = round(principal + interest, 2)
                    else:
                        emi = new_emi
                    rem = max(round(rem - principal, 2), 0.0)
                    pay_date = start_date + relativedelta(months=i-1)
                    db.session.add(Schedule(loan_id=loan.id, month_index=start_idx + i,
                                            payment_date=pay_date, emi=emi, principal=principal,
                                            interest=interest, remaining_balance=rem, is_revised=True))
                loan.tenure_months = start_idx + form.new_tenure.data
                summary = f"Tenure adjusted to {form.new_tenure.data} unpaid months"
        elif rtype == "EXTRA" and form.extra_amount.data:
            # apply extra monthly: reduce EMI's effective principal each month
            unpaid = sorted([s for s in loan.schedules if s.payment_status != "Paid"], key=lambda x: x.month_index)
            monthly_rate = (loan.interest_rate / 100.0) / 12.0
            rem = loan.remaining_balance
            cleared_at = None
            for s in unpaid:
                interest = round(rem * monthly_rate, 2)
                principal = round((s.emi - interest) + form.extra_amount.data, 2)
                if principal >= rem:
                    principal = round(rem, 2)
                    s.emi = round(principal + interest, 2)
                    s.principal = principal
                    s.interest = interest
                    s.remaining_balance = 0
                    s.is_revised = True
                    cleared_at = s.month_index
                    # remove subsequent unpaid
                    for later in unpaid:
                        if later.month_index > s.month_index:
                            db.session.delete(later)
                    break
                else:
                    s.principal = principal
                    s.interest = interest
                    s.emi = round(principal + interest, 2)
                    rem = round(rem - principal, 2)
                    s.remaining_balance = rem
                    s.is_revised = True
            summary = f"Extra {form.extra_amount.data}/month applied" + (f" — closes at installment {cleared_at}" if cleared_at else "")
        elif rtype == "LUMPSUM" and form.extra_amount.data:
            recalc_with_lumpsum(loan, form.extra_amount.data)
            summary = f"Lump-sum {form.extra_amount.data} applied"
        elif rtype == "PAYOFF":
            simulation = {"payoff_today": loan.remaining_balance}
            summary = f"Simulated early payoff = {loan.remaining_balance:.2f}"
            db.session.add(RecalculationHistory(loan_id=loan.id, recalc_type=rtype, payload="", summary=summary))
            db.session.add(ActivityLog(user_id=current_user.id, loan_id=loan.id, action="RECALC", detail=summary))
            db.session.commit()
            flash(summary, "info")
            return render_template("recalculate/index.html", loans=loans, loan=loan, form=form, simulation=simulation)
        update_loan_progress(loan)
        db.session.add(RecalculationHistory(loan_id=loan.id, recalc_type=rtype,
                                            payload=str(request.form.to_dict()), summary=summary))
        db.session.add(ActivityLog(user_id=current_user.id, loan_id=loan.id, action="RECALC", detail=summary))
        db.session.commit()
        flash("Recalculation applied to remaining installments.", "success")
        return redirect(url_for("recalc.index", loan_pk=loan.id))
    return render_template("recalculate/index.html", loans=loans, loan=loan, form=form, simulation=simulation)
