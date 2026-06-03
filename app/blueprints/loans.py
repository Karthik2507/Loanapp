from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import Loan, Schedule, ActivityLog, LoanAuditLog, BalloonPayment
from app.forms import LoanForm
from app.utils import generate_amortization, update_loan_progress

loans_bp = Blueprint("loans", __name__, url_prefix="/loans")


def _get_loan_or_404(loan_pk):
    loan = Loan.query.filter_by(id=loan_pk, user_id=current_user.id).first()
    if not loan:
        abort(404)
    return loan


@loans_bp.route("/")
@login_required
def list_loans():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    page = int(request.args.get("page", 1))
    query = current_user.loans.filter_by(is_archived=False)
    if q:
        like = f"%{q}%"
        query = query.filter((Loan.loan_id.ilike(like)) | (Loan.loan_name.ilike(like)) | (Loan.bank_name.ilike(like)))
    if status:
        query = query.filter_by(loan_status=status)
    pagination = query.order_by(Loan.created_at.desc()).paginate(page=page, per_page=10, error_out=False)
    return render_template("loans/list.html", pagination=pagination, q=q, status=status)


@loans_bp.route("/archived")
@login_required
def archived():
    items = current_user.loans.filter_by(is_archived=True).order_by(Loan.updated_at.desc()).all()
    return render_template("loans/archived.html", items=items)


@loans_bp.route("/add", methods=["GET", "POST"])
@login_required
def add():
    form = LoanForm()
    if form.validate_on_submit():
        if Loan.query.filter_by(user_id=current_user.id, loan_id=form.loan_id.data.strip()).first():
            flash("Loan ID already exists. Choose a unique one.", "danger")
            return render_template("loans/form.html", form=form, mode="add")
        loan = Loan(
            user_id=current_user.id,
            loan_id=form.loan_id.data.strip(),
            loan_name=form.loan_name.data.strip(),
            loan_category=form.loan_category.data,
            bank_name=form.bank_name.data.strip(),
            loan_amount=form.loan_amount.data,
            interest_rate=form.interest_rate.data,
            down_payment=form.down_payment.data or 0,
            custom_emi=form.custom_emi.data,
            start_date=form.start_date.data,
            tenure_months=form.tenure_months.data,
            balloon_date=form.balloon_date.data,
            balloon_amount=form.balloon_amount.data,
            notes=form.notes.data,
        )
        db.session.add(loan)
        db.session.flush()
        # generate schedule once
        rows = generate_amortization(loan)
        for r in rows:
            db.session.add(Schedule(loan_id=loan.id, **r))
        if loan.balloon_date and loan.balloon_amount:
            db.session.add(BalloonPayment(loan_id=loan.id, due_date=loan.balloon_date, amount=loan.balloon_amount))
        update_loan_progress(loan)
        db.session.add(ActivityLog(user_id=current_user.id, loan_id=loan.id, action="CREATE_LOAN", detail=f"{loan.loan_id} — {loan.loan_name}"))
        db.session.commit()
        flash("Loan created and amortization schedule generated.", "success")
        return redirect(url_for("loans.details", loan_pk=loan.id))
    return render_template("loans/form.html", form=form, mode="add")


@loans_bp.route("/<int:loan_pk>/edit", methods=["GET", "POST"])
@login_required
def edit(loan_pk):
    loan = _get_loan_or_404(loan_pk)
    form = LoanForm(obj=loan)
    if form.validate_on_submit():
        for field in ("loan_name", "loan_category", "bank_name", "notes"):
            old = getattr(loan, field)
            new = getattr(form, field).data
            if old != new:
                db.session.add(LoanAuditLog(loan_id=loan.id, field=field, old_value=str(old), new_value=str(new)))
        loan.loan_name = form.loan_name.data
        loan.loan_category = form.loan_category.data
        loan.bank_name = form.bank_name.data
        loan.notes = form.notes.data
        db.session.add(ActivityLog(user_id=current_user.id, loan_id=loan.id, action="EDIT_LOAN", detail="Metadata updated"))
        db.session.commit()
        flash("Loan updated. (Core financials are immutable once a schedule exists; use Recalculate.)", "info")
        return redirect(url_for("loans.details", loan_pk=loan.id))
    return render_template("loans/form.html", form=form, mode="edit", loan=loan)


@loans_bp.route("/<int:loan_pk>")
@login_required
def details(loan_pk):
    loan = _get_loan_or_404(loan_pk)
    return render_template("loans/details.html", loan=loan)


@loans_bp.route("/<int:loan_pk>/archive", methods=["POST"])
@login_required
def archive(loan_pk):
    loan = _get_loan_or_404(loan_pk)
    loan.is_archived = True
    loan.loan_status = "Archived"
    db.session.add(ActivityLog(user_id=current_user.id, loan_id=loan.id, action="ARCHIVE_LOAN", detail=loan.loan_id))
    db.session.commit()
    flash("Loan archived.", "info")
    return redirect(url_for("loans.list_loans"))


@loans_bp.route("/<int:loan_pk>/restore", methods=["POST"])
@login_required
def restore(loan_pk):
    loan = _get_loan_or_404(loan_pk)
    loan.is_archived = False
    update_loan_progress(loan)
    db.session.add(ActivityLog(user_id=current_user.id, loan_id=loan.id, action="RESTORE_LOAN", detail=loan.loan_id))
    db.session.commit()
    flash("Loan restored.", "success")
    return redirect(url_for("loans.archived"))


@loans_bp.route("/<int:loan_pk>/delete", methods=["POST"])
@login_required
def delete(loan_pk):
    loan = _get_loan_or_404(loan_pk)
    db.session.add(ActivityLog(user_id=current_user.id, loan_id=None, action="DELETE_LOAN", detail=f"{loan.loan_id} ({loan.loan_name})"))
    db.session.delete(loan)
    db.session.commit()
    flash("Loan deleted permanently.", "warning")
    return redirect(url_for("loans.list_loans"))


@loans_bp.route("/<int:loan_pk>/close", methods=["POST"])
@login_required
def close(loan_pk):
    from datetime import datetime
    loan = _get_loan_or_404(loan_pk)
    unpaid = [s for s in loan.schedules if s.payment_status != "Paid"]
    if unpaid or loan.remaining_balance > 0.01:
        flash("Closure not allowed: outstanding installments or balance remain.", "danger")
        return redirect(url_for("loans.details", loan_pk=loan.id))
    loan.loan_status = "Completed"
    loan.closed_at = datetime.utcnow()
    loan.final_amount = sum(s.emi for s in loan.schedules)
    loan.closure_notes = request.form.get("closure_notes", "")
    db.session.add(ActivityLog(user_id=current_user.id, loan_id=loan.id, action="CLOSE_LOAN", detail=loan.loan_id))
    db.session.commit()
    flash("Loan closed.", "success")
    return redirect(url_for("loans.details", loan_pk=loan.id))
