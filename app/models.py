from datetime import datetime, date
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    preferred_currency = db.Column(db.String(8), default="INR")
    preferred_date_format = db.Column(db.String(20), default="%d %b %Y")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    loans = db.relationship("Loan", backref="owner", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class LoanCategory(db.Model):
    __tablename__ = "loan_categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


class Loan(db.Model):
    __tablename__ = "loans"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    loan_id = db.Column(db.String(40), nullable=False, index=True)  # manual unique per user
    loan_name = db.Column(db.String(120), nullable=False)
    loan_category = db.Column(db.String(50), nullable=False, default="Personal")
    bank_name = db.Column(db.String(120), nullable=False)
    loan_amount = db.Column(db.Float, nullable=False)
    interest_rate = db.Column(db.Float, nullable=False)  # annual %
    down_payment = db.Column(db.Float, default=0)
    start_date = db.Column(db.Date, nullable=False)
    tenure_months = db.Column(db.Integer, nullable=False)
    loan_status = db.Column(db.String(20), default="Active", index=True)
    remaining_balance = db.Column(db.Float, default=0)
    completion_percentage = db.Column(db.Float, default=0)
    is_archived = db.Column(db.Boolean, default=False, index=True)
    # balloon
    balloon_date = db.Column(db.Date, nullable=True)
    balloon_amount = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text)
    closed_at = db.Column(db.DateTime, nullable=True)
    final_amount = db.Column(db.Float, nullable=True)
    closure_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    schedules = db.relationship("Schedule", backref="loan", lazy="dynamic",
                                cascade="all, delete-orphan", order_by="Schedule.month_index")

    __table_args__ = (db.UniqueConstraint("user_id", "loan_id", name="uq_user_loanid"),)


class Schedule(db.Model):
    __tablename__ = "schedules"
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False, index=True)
    month_index = db.Column(db.Integer, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    emi = db.Column(db.Float, nullable=False)
    principal = db.Column(db.Float, nullable=False)
    interest = db.Column(db.Float, nullable=False)
    remaining_balance = db.Column(db.Float, nullable=False)
    payment_status = db.Column(db.String(20), default="Pending")  # Pending / Paid / Overdue
    paid_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.String(255))
    is_balloon = db.Column(db.Boolean, default=False)
    is_revised = db.Column(db.Boolean, default=False)


class PaymentHistory(db.Model):
    __tablename__ = "payment_history"
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False, index=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey("schedules.id"), nullable=True)
    action = db.Column(db.String(20))  # PAID / UNDO
    amount = db.Column(db.Float)
    notes = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=True)
    action = db.Column(db.String(80))
    detail = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class InterestRateHistory(db.Model):
    __tablename__ = "interest_rate_history"
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False, index=True)
    previous_rate = db.Column(db.Float, nullable=False)
    new_rate = db.Column(db.Float, nullable=False)
    effective_date = db.Column(db.Date, nullable=False)
    effective_installment = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class RecalculationHistory(db.Model):
    __tablename__ = "recalculation_history"
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False, index=True)
    recalc_type = db.Column(db.String(40))  # EMI / TENURE / EXTRA / LUMPSUM / PAYOFF / RATE
    payload = db.Column(db.String(500))
    summary = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BalloonPayment(db.Model):
    __tablename__ = "balloon_payments"
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False, index=True)
    due_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    paid = db.Column(db.Boolean, default=False)
    paid_date = db.Column(db.Date, nullable=True)


class LoanAuditLog(db.Model):
    __tablename__ = "loan_audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False, index=True)
    field = db.Column(db.String(60))
    old_value = db.Column(db.String(255))
    new_value = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Setting(db.Model):
    __tablename__ = "settings"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    key = db.Column(db.String(60))
    value = db.Column(db.String(255))
