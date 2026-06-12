from app import create_app, db
from app.seed import seed_demo_data

app = create_app()

@app.cli.command("init-db")
def init_db():
    with app.app_context():
        db.create_all()
        print("Database initialized.")

@app.cli.command("seed")
def seed():
    with app.app_context():
        db.create_all()
        seed_demo_data()
        print("Seed data inserted.")


@app.cli.command("check-reminders")
def check_reminders():
    from app.models import User, Loan, Schedule, Setting
    from datetime import date, timedelta
    
    with app.app_context():
        users = User.query.all()
        print("Checking installment reminders...")
        for u in users:
            enabled_setting = Setting.query.filter_by(user_id=u.id, key="reminders_enabled").first()
            if not enabled_setting or enabled_setting.value != "true":
                continue
                
            days_setting = Setting.query.filter_by(user_id=u.id, key="reminder_days_before").first()
            days = int(days_setting.value) if days_setting and days_setting.value else 5
            
            target_date = date.today() + timedelta(days=days)
            
            loans = u.loans.filter_by(is_archived=False).all()
            for l in loans:
                if l.loan_status == "Completed":
                    continue
                due_schedule = l.schedules.filter(
                    Schedule.payment_status != "Paid",
                    Schedule.payment_date == target_date
                ).first()
                
                if due_schedule:
                    email_setting = Setting.query.filter_by(user_id=u.id, key="reminder_email").first()
                    dest_email = email_setting.value if email_setting and email_setting.value else u.email
                    
                    print(f"[ALERT] Sending reminder to {dest_email} for loan {l.loan_id} ({l.loan_name}).")
                    print(f"        Installment #{due_schedule.month_index} of {due_schedule.emi} is due on {due_schedule.payment_date}.")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0", port=5000)

