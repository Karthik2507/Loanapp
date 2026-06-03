from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import Loan, Schedule, PaymentHistory, ActivityLog, InterestRateHistory
from app.forms import InterestRevisionForm
from app.utils import update_loan_progress, recalc_unpaid_with_new_rate

schedule_bp = Blueprint("schedule", __name__, url_prefix="/schedule")


def _get_loan(loan_pk):
    loan = Loan.query.filter_by(id=loan_pk, user_id=current_user.id).first()
    if not loan:
        abort(404)
    return loan


@schedule_bp.route("/")
@login_required
def index():
    loans = current_user.loans.filter_by(is_archived=False).order_by(Loan.created_at.desc()).all()
    selected_id = request.args.get("loan_pk", type=int)
    loan = _get_loan(selected_id) if selected_id else (loans[0] if loans else None)
    revision_form = InterestRevisionForm()
    return render_template("schedule/index.html", loans=loans, loan=loan, revision_form=revision_form)


@schedule_bp.route("/<int:loan_pk>")
@login_required
def view(loan_pk):
    loan = _get_loan(loan_pk)
    loans = current_user.loans.filter_by(is_archived=False).all()
    revision_form = InterestRevisionForm()
    return render_template("schedule/index.html", loans=loans, loan=loan, revision_form=revision_form)


@schedule_bp.route("/<int:loan_pk>/mark-paid/<int:schedule_id>", methods=["POST"])
@login_required
def mark_paid(loan_pk, schedule_id):
    loan = _get_loan(loan_pk)
    s = Schedule.query.filter_by(id=schedule_id, loan_id=loan.id).first_or_404()
    s.payment_status = "Paid"
    s.paid_date = date.today()
    s.notes = request.form.get("notes", "") or s.notes
    db.session.add(PaymentHistory(loan_id=loan.id, schedule_id=s.id, action="PAID", amount=s.emi, notes=s.notes))
    db.session.add(ActivityLog(user_id=current_user.id, loan_id=loan.id, action="MARK_PAID", detail=f"Installment {s.month_index}"))
    update_loan_progress(loan)
    db.session.commit()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        from flask import jsonify
        paid_date_str = s.paid_date.strftime(current_user.preferred_date_format)
        return jsonify({"ok": True, "loan_status": loan.loan_status,
                        "remaining_balance": loan.remaining_balance,
                        "completion_percentage": loan.completion_percentage,
                        "paid_date": paid_date_str})
    flash(f"Installment #{s.month_index} marked paid.", "success")
    return redirect(url_for("schedule.view", loan_pk=loan.id))


@schedule_bp.route("/<int:loan_pk>/undo-paid/<int:schedule_id>", methods=["POST"])
@login_required
def undo_paid(loan_pk, schedule_id):
    loan = _get_loan(loan_pk)
    s = Schedule.query.filter_by(id=schedule_id, loan_id=loan.id).first_or_404()
    s.payment_status = "Pending"
    s.paid_date = None
    db.session.add(PaymentHistory(loan_id=loan.id, schedule_id=s.id, action="UNDO", amount=s.emi, notes="Undo"))
    db.session.add(ActivityLog(user_id=current_user.id, loan_id=loan.id, action="UNDO_PAID", detail=f"Installment {s.month_index}"))
    update_loan_progress(loan)
    db.session.commit()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        from flask import jsonify
        return jsonify({"ok": True, "loan_status": loan.loan_status,
                        "remaining_balance": loan.remaining_balance,
                        "completion_percentage": loan.completion_percentage})
    flash(f"Installment #{s.month_index} unmarked.", "info")
    return redirect(url_for("schedule.view", loan_pk=loan.id))


@schedule_bp.route("/<int:loan_pk>/revise-interest", methods=["POST"])
@login_required
def revise_interest(loan_pk):
    loan = _get_loan(loan_pk)
    form = InterestRevisionForm()
    if not form.validate_on_submit():
        flash("Invalid revision input.", "danger")
        return redirect(url_for("schedule.view", loan_pk=loan.id))
    unpaid = [s for s in loan.schedules if s.payment_status != "Paid"]
    if not unpaid:
        flash("Nothing to revise — no unpaid installments.", "warning")
        return redirect(url_for("schedule.view", loan_pk=loan.id))
    first_unpaid = min(unpaid, key=lambda s: s.month_index)
    db.session.add(InterestRateHistory(
        loan_id=loan.id,
        previous_rate=loan.interest_rate,
        new_rate=form.new_rate.data,
        effective_date=form.effective_date.data,
        effective_installment=first_unpaid.month_index,
    ))
    recalc_unpaid_with_new_rate(loan, form.new_rate.data, form.effective_date.data)
    loan.interest_rate = form.new_rate.data
    update_loan_progress(loan)
    db.session.add(ActivityLog(user_id=current_user.id, loan_id=loan.id, action="REVISE_RATE",
                               detail=f"New rate {form.new_rate.data}% from installment {first_unpaid.month_index}"))
    db.session.commit()
    flash("Interest rate revised for remaining installments.", "success")
    return redirect(url_for("schedule.view", loan_pk=loan.id))


@schedule_bp.route("/<int:loan_pk>/annual-summary/csv")
@login_required
def annual_summary_csv(loan_pk):
    import csv
    import io
    from flask import Response
    
    loan = _get_loan(loan_pk)
    schedules = loan.schedules.all()
    
    # Group by year
    years_data = {}
    for s in schedules:
        year = s.payment_date.year
        if year not in years_data:
            years_data[year] = {"principal": 0.0, "interest": 0.0, "payment": 0.0}
        years_data[year]["principal"] += s.principal
        years_data[year]["interest"] += s.interest
        years_data[year]["payment"] += s.emi
        
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["Year", "Total Principal", "Total Interest", "Total Payment"])
    
    grand_principal = 0.0
    grand_interest = 0.0
    grand_payment = 0.0
    
    sorted_years = sorted(years_data.keys())
    for y in sorted_years:
        p = years_data[y]["principal"]
        i = years_data[y]["interest"]
        pay = years_data[y]["payment"]
        w.writerow([y, f"{p:.2f}", f"{i:.2f}", f"{pay:.2f}"])
        grand_principal += p
        grand_interest += i
        grand_payment += pay
        
    w.writerow(["Grand Total", f"{grand_principal:.2f}", f"{grand_interest:.2f}", f"{grand_payment:.2f}"])
    
    filename = f"annual_summary_{loan.loan_id}.csv"
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})