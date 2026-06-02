from datetime import date, timedelta
from app import db
from app.models import User, Loan, Schedule, ActivityLog, BalloonPayment
from app.utils import generate_amortization, update_loan_progress


def seed_demo_data():
    if User.query.filter_by(username="demo").first():
        print("Demo user already exists; skipping seed.")
        return
    u = User(full_name="Demo User", username="demo", email="demo@loanledger.app",
             preferred_currency="INR", preferred_date_format="%d %b %Y")
    u.set_password("Demo@1234")
    db.session.add(u)
    db.session.flush()

    samples = [
        dict(loan_id="HOME001", loan_name="Home Loan — Mumbai Flat", loan_category="Home",
             bank_name="HDFC Bank", loan_amount=4500000, interest_rate=8.5,
             down_payment=500000, start_date=date.today() - timedelta(days=365*2),
             tenure_months=240),
        dict(loan_id="AUTO007", loan_name="SUV Auto Loan", loan_category="Auto",
             bank_name="ICICI Bank", loan_amount=900000, interest_rate=9.25,
             down_payment=100000, start_date=date.today() - timedelta(days=365),
             tenure_months=60, balloon_date=date.today() + timedelta(days=30), balloon_amount=350000),
        dict(loan_id="EDU003", loan_name="MBA Education Loan", loan_category="Education",
             bank_name="SBI", loan_amount=1500000, interest_rate=10.5,
             down_payment=0, start_date=date.today() - timedelta(days=180),
             tenure_months=84),
        dict(loan_id="BIZ012", loan_name="Working Capital", loan_category="Business",
             bank_name="Axis Bank", loan_amount=2000000, interest_rate=11.0,
             down_payment=0, start_date=date.today() - timedelta(days=90),
             tenure_months=36),
    ]
    for data in samples:
        l = Loan(user_id=u.id, **data)
        db.session.add(l)
        db.session.flush()
        for r in generate_amortization(l):
            db.session.add(Schedule(loan_id=l.id, **r))
        if l.balloon_date and l.balloon_amount:
            db.session.add(BalloonPayment(loan_id=l.id, due_date=l.balloon_date, amount=l.balloon_amount))
        # mark some installments paid
        scheds = sorted(l.schedules, key=lambda s: s.month_index)
        paid_count = min(len(scheds) // 4, 18)
        for s in scheds[:paid_count]:
            s.payment_status = "Paid"
            s.paid_date = s.payment_date
        update_loan_progress(l)
        db.session.add(ActivityLog(user_id=u.id, loan_id=l.id, action="SEED", detail=f"Seeded {l.loan_id}"))
    db.session.commit()
    print("Demo data seeded. Login: demo / Demo@1234")
