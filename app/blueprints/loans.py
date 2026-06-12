from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import Loan, Schedule, ActivityLog, LoanAuditLog, BalloonPayment
from app.forms import LoanForm
from app.utils import generate_amortization, update_loan_progress, emi_amount

loans_bp = Blueprint("loans", __name__, url_prefix="/loans")


def recalculate_unpaid_schedules(loan):
    from app.models import Schedule, BalloonPayment
    from dateutil.relativedelta import relativedelta
    from datetime import date
    
    paid_schedules = Schedule.query.filter_by(loan_id=loan.id, payment_status='Paid').all()
    if not paid_schedules:
        Schedule.query.filter_by(loan_id=loan.id).delete()
        db.session.flush()
        
        rows = generate_amortization(loan)
        for r in rows:
            db.session.add(Schedule(loan_id=loan.id, **r))
            
        BalloonPayment.query.filter_by(loan_id=loan.id).delete()
        if loan.balloon_date and loan.balloon_amount:
            db.session.add(BalloonPayment(loan_id=loan.id, due_date=loan.balloon_date, amount=loan.balloon_amount))
            
        update_loan_progress(loan)
        return
        
    paid_count = len(paid_schedules)
    last_paid = max(paid_schedules, key=lambda s: s.month_index)
    remaining_principal = last_paid.remaining_balance
    start_idx = last_paid.month_index
    start_date = last_paid.payment_date
    
    unpaid_count = max(loan.tenure_months - paid_count, 1)
    
    if loan.custom_emi:
        emi = float(loan.custom_emi)
    else:
        emi = emi_amount(remaining_principal, loan.interest_rate, unpaid_count)
        
    Schedule.query.filter((Schedule.loan_id == loan.id) & (Schedule.payment_status != 'Paid')).delete()
    db.session.flush()
    
    monthly_rate = (loan.interest_rate / 100.0) / 12.0
    rem = remaining_principal
    
    for i in range(1, unpaid_count + 1):
        pay_date = start_date + relativedelta(months=i)
        interest = max(round(rem * monthly_rate, 2), 0.0)
        principal_component = round(emi - interest, 2)
        
        if loan.balloon_date and pay_date >= loan.balloon_date:
            principal_component = round(rem, 2)
            emi_row = round(principal_component + interest, 2)
            rem = 0.0
            db.session.add(Schedule(
                loan_id=loan.id,
                month_index=start_idx + i,
                payment_date=pay_date,
                emi=emi_row,
                principal=principal_component,
                interest=interest,
                remaining_balance=0.0,
                payment_status="Pending",
                is_balloon=True,
                is_revised=True
            ))
            break

        if principal_component >= rem or i == unpaid_count:
            principal_component = round(rem, 2)
            emi_row = round(principal_component + interest, 2)
            rem = 0.0
            db.session.add(Schedule(
                loan_id=loan.id,
                month_index=start_idx + i,
                payment_date=pay_date,
                emi=emi_row,
                principal=principal_component,
                interest=interest,
                remaining_balance=0.0,
                payment_status="Pending",
                is_balloon=False,
                is_revised=True
            ))
            break

        rem = round(rem - principal_component, 2)
        db.session.add(Schedule(
            loan_id=loan.id,
            month_index=start_idx + i,
            payment_date=pay_date,
            emi=emi,
            principal=principal_component,
            interest=interest,
            remaining_balance=max(rem, 0.0),
            payment_status="Pending",
            is_balloon=False,
            is_revised=True
        ))
        
    if loan.balloon_date and loan.balloon_amount:
        bp = BalloonPayment.query.filter_by(loan_id=loan.id).first()
        if bp:
            if not bp.paid:
                bp.due_date = loan.balloon_date
                bp.amount = loan.balloon_amount
        else:
            db.session.add(BalloonPayment(loan_id=loan.id, due_date=loan.balloon_date, amount=loan.balloon_amount))
    else:
        BalloonPayment.query.filter_by(loan_id=loan.id, paid=False).delete()
        
    update_loan_progress(loan)


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
            tenure_months=int(round(form.tenure_months.data * 12)) if form.tenure_unit.data == "years" else int(form.tenure_months.data),
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
    
    # Fetch audit and activity logs
    audit_logs = LoanAuditLog.query.filter_by(loan_id=loan.id).all()
    activity_logs = ActivityLog.query.filter_by(loan_id=loan.id).all()
    
    # Format and merge history logs
    history = []
    for a in audit_logs:
        history.append({
            "type": "audit",
            "title": f"Field '{a.field.replace('_', ' ').title()}' updated",
            "detail": f"Changed from '{a.old_value}' to '{a.new_value}'",
            "date": a.created_at
        })
    for act in activity_logs:
        history.append({
            "type": "activity",
            "title": act.action.replace("_", " ").title(),
            "detail": act.detail or "",
            "date": act.created_at
        })
        
    history.sort(key=lambda x: x["date"], reverse=True)
    
    # Compute active loan remaining interest and tenure for refinance simulation
    unpaid_schedules = [s for s in loan.schedules if s.payment_status != "Paid"]
    remaining_interest = sum(s.interest for s in unpaid_schedules)
    remaining_tenure = len(unpaid_schedules)
    
    return render_template(
        "loans/details.html", 
        loan=loan, 
        history=history,
        remaining_interest=round(remaining_interest, 2),
        remaining_tenure=remaining_tenure
    )


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


@loans_bp.route("/bulk-upload", methods=["POST"])
@login_required
def bulk_upload():
    from datetime import datetime, date
    
    data = request.get_json()
    if not data or not isinstance(data, list):
        return {"success": False, "message": "Invalid payload format."}, 400
        
    created_count = 0
    updated_count = 0
    skipped_count = 0
    
    def parse_date(date_str):
        if not date_str:
            return None
        if isinstance(date_str, date):
            return date_str
        try:
            return datetime.strptime(date_str.split('T')[0], "%Y-%m-%d").date()
        except ValueError:
            try:
                return datetime.strptime(date_str, "%d/%m/%Y").date()
            except ValueError:
                try:
                    return datetime.strptime(date_str, "%m/%d/%Y").date()
                except ValueError:
                    return None

    def check_if_same(loan, row):
        def float_eq(v1, v2):
            f1 = float(v1) if v1 is not None else 0.0
            f2 = float(v2) if v2 is not None and str(v2).strip() != "" else 0.0
            return abs(f1 - f2) < 0.001

        def date_eq(d1, d2):
            if not d1 and not d2:
                return True
            if not d1 or not d2:
                return False
            p1 = parse_date(d1) if isinstance(d1, str) else d1
            p2 = parse_date(d2) if isinstance(d2, str) else d2
            return p1 == p2

        if (loan.loan_name or "").strip() != (row.get("loan_name") or "").strip():
            return False
        if (loan.loan_category or "").strip() != (row.get("loan_category") or "").strip():
            return False
        if (loan.bank_name or "").strip() != (row.get("bank_name") or "").strip():
            return False
        if (loan.notes or "").strip() != (row.get("notes") or "").strip():
            return False

        if not float_eq(loan.loan_amount, row.get("loan_amount")):
            return False
        if not float_eq(loan.interest_rate, row.get("interest_rate")):
            return False
        if not float_eq(loan.down_payment, row.get("down_payment")):
            return False
        if not float_eq(loan.custom_emi, row.get("custom_emi")):
            return False
        if not float_eq(loan.balloon_amount, row.get("balloon_amount")):
            return False

        if not date_eq(loan.start_date, row.get("start_date")):
            return False
        if not date_eq(loan.balloon_date, row.get("balloon_date")):
            return False

        tenure_val = float(row.get("tenure_months") or 0)
        tenure_unit = (row.get("tenure_unit") or "months").strip().lower()
        uploaded_tenure_months = int(round(tenure_val * 12)) if tenure_unit == "years" else int(tenure_val)
        if loan.tenure_months != uploaded_tenure_months:
            return False

        return True

    for row in data:
        loan_id = str(row.get("loan_id", "")).strip()
        if not loan_id:
            continue
            
        existing_loan = Loan.query.filter_by(user_id=current_user.id, loan_id=loan_id).first()
        
        loan_name = str(row.get("loan_name") or f"Loan {loan_id}").strip()
        loan_category = str(row.get("loan_category") or "Personal").strip()
        valid_cats = ["Home", "Auto", "Personal", "Education", "Business", "Gold", "Other"]
        if loan_category not in valid_cats:
            loan_category = "Personal"
            
        bank_name = str(row.get("bank_name") or "Other").strip()
        loan_amount = float(row.get("loan_amount") or 0)
        interest_rate = float(row.get("interest_rate") or 0)
        down_payment = float(row.get("down_payment") or 0)
        custom_emi = row.get("custom_emi")
        custom_emi = float(custom_emi) if custom_emi is not None and str(custom_emi).strip() != "" else None
        
        tenure_val = float(row.get("tenure_months") or 0)
        tenure_unit = str(row.get("tenure_unit") or "months").strip().lower()
        tenure_months = int(round(tenure_val * 12)) if tenure_unit == "years" else int(tenure_val)
        
        start_date = parse_date(row.get("start_date"))
        balloon_date = parse_date(row.get("balloon_date"))
        balloon_amount = row.get("balloon_amount")
        balloon_amount = float(balloon_amount) if balloon_amount is not None and str(balloon_amount).strip() != "" else None
        
        notes = str(row.get("notes") or "").strip()
        
        if not start_date or tenure_months <= 0 or interest_rate < 0 or loan_amount <= 0:
            continue
            
        if existing_loan:
            if check_if_same(existing_loan, row):
                skipped_count += 1
                continue
                
            for field, old, new in [
                ("loan_name", existing_loan.loan_name, loan_name),
                ("loan_category", existing_loan.loan_category, loan_category),
                ("bank_name", existing_loan.bank_name, bank_name),
                ("loan_amount", existing_loan.loan_amount, loan_amount),
                ("interest_rate", existing_loan.interest_rate, interest_rate),
                ("down_payment", existing_loan.down_payment, down_payment),
                ("custom_emi", existing_loan.custom_emi, custom_emi),
                ("start_date", existing_loan.start_date, start_date),
                ("tenure_months", existing_loan.tenure_months, tenure_months),
                ("balloon_date", existing_loan.balloon_date, balloon_date),
                ("balloon_amount", existing_loan.balloon_amount, balloon_amount),
                ("notes", existing_loan.notes, notes)
            ]:
                if old != new:
                    db.session.add(LoanAuditLog(loan_id=existing_loan.id, field=field, old_value=str(old), new_value=str(new)))
            
            existing_loan.loan_name = loan_name
            existing_loan.loan_category = loan_category
            existing_loan.bank_name = bank_name
            existing_loan.loan_amount = loan_amount
            existing_loan.interest_rate = interest_rate
            existing_loan.down_payment = down_payment
            existing_loan.custom_emi = custom_emi
            existing_loan.start_date = start_date
            existing_loan.tenure_months = tenure_months
            existing_loan.balloon_date = balloon_date
            existing_loan.balloon_amount = balloon_amount
            existing_loan.notes = notes
            
            db.session.flush()
            recalculate_unpaid_schedules(existing_loan)
            
            db.session.add(ActivityLog(user_id=current_user.id, loan_id=existing_loan.id, action="EDIT_LOAN", detail="Bulk load update"))
            updated_count += 1
        else:
            loan = Loan(
                user_id=current_user.id,
                loan_id=loan_id,
                loan_name=loan_name,
                loan_category=loan_category,
                bank_name=bank_name,
                loan_amount=loan_amount,
                interest_rate=interest_rate,
                down_payment=down_payment,
                custom_emi=custom_emi,
                start_date=start_date,
                tenure_months=tenure_months,
                balloon_date=balloon_date,
                balloon_amount=balloon_amount,
                notes=notes
            )
            db.session.add(loan)
            db.session.flush()
            
            rows_sch = generate_amortization(loan)
            for r in rows_sch:
                db.session.add(Schedule(loan_id=loan.id, **r))
                
            if loan.balloon_date and loan.balloon_amount:
                db.session.add(BalloonPayment(loan_id=loan.id, due_date=loan.balloon_date, amount=loan.balloon_amount))
                
            update_loan_progress(loan)
            db.session.add(ActivityLog(user_id=current_user.id, loan_id=loan.id, action="CREATE_LOAN", detail=f"{loan.loan_id} — {loan.loan_name} (Bulk load)"))
            created_count += 1
            
    db.session.commit()
    return {
        "success": True,
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count
    }


@loans_bp.route("/active-loans-data", methods=["GET"])
@login_required
def active_loans_data():
    loans = Loan.query.filter_by(user_id=current_user.id, is_archived=False).filter(Loan.loan_status != 'Completed').all()
    res = []
    for l in loans:
        res.append({
            "loan_id": l.loan_id,
            "loan_name": l.loan_name,
            "loan_category": l.loan_category,
            "bank_name": l.bank_name,
            "loan_amount": l.loan_amount,
            "custom_emi": l.custom_emi if l.custom_emi else "",
            "interest_rate": l.interest_rate,
            "down_payment": l.down_payment or 0,
            "start_date": l.start_date.strftime("%Y-%m-%d") if l.start_date else "",
            "tenure_months": l.tenure_months,
            "tenure_unit": "months",
            "balloon_date": l.balloon_date.strftime("%Y-%m-%d") if l.balloon_date else "",
            "balloon_amount": l.balloon_amount if l.balloon_amount else "",
            "notes": l.notes or ""
        })
    return {"success": True, "loans": res}

