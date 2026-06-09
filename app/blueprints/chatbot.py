import os
from datetime import datetime, date
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Loan, Schedule, ActivityLog, LoanAuditLog, Setting
from app.utils import generate_amortization, update_loan_progress, emi_amount, recalc_unpaid_with_new_rate

chatbot_bp = Blueprint("chatbot", __name__, url_prefix="/chatbot")

# Tool Functions for Gemini

def list_loans():
    """List all active and archived loans for the current user."""
    loans = Loan.query.filter_by(user_id=current_user.id).all()
    return [{
        "loan_id": l.loan_id,
        "loan_name": l.loan_name,
        "loan_amount": l.loan_amount,
        "interest_rate": l.interest_rate,
        "tenure_months": l.tenure_months,
        "loan_category": l.loan_category,
        "bank_name": l.bank_name,
        "loan_status": l.loan_status,
        "remaining_balance": l.remaining_balance,
        "is_archived": l.is_archived
    } for l in loans]


def get_loan_details(loan_id: str):
    """Retrieve detailed information and status for a specific loan by its unique loan_id."""
    loan = Loan.query.filter_by(user_id=current_user.id, loan_id=loan_id.strip()).first()
    if not loan:
        return {"error": f"Loan with ID '{loan_id}' not found."}
    return {
        "loan_id": loan.loan_id,
        "loan_name": loan.loan_name,
        "loan_amount": loan.loan_amount,
        "interest_rate": loan.interest_rate,
        "tenure_months": loan.tenure_months,
        "loan_category": loan.loan_category,
        "bank_name": loan.bank_name,
        "loan_status": loan.loan_status,
        "remaining_balance": loan.remaining_balance,
        "completion_percentage": loan.completion_percentage,
        "notes": loan.notes,
        "start_date": str(loan.start_date),
        "down_payment": loan.down_payment,
        "custom_emi": loan.custom_emi
    }


def create_loan(
    loan_id: str,
    loan_name: str,
    loan_category: str,
    bank_name: str,
    loan_amount: float,
    interest_rate: float,
    tenure_months: int,
    start_date: str,
    down_payment: float = 0.0,
    custom_emi: float = None,
    notes: str = None
):
    """Create a new loan with the specified details.
    All rates are in % (e.g. 5.5), and start_date must be in YYYY-MM-DD format.
    """
    loan_id = loan_id.strip()
    existing = Loan.query.filter_by(user_id=current_user.id, loan_id=loan_id).first()
    if existing:
        return {"error": f"A loan with ID '{loan_id}' already exists."}
    
    try:
        parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Invalid start_date format. Must be YYYY-MM-DD."}
        
    valid_categories = ["Home", "Auto", "Personal", "Education", "Business", "Gold", "Other"]
    category = loan_category.title() if loan_category else "Personal"
    if category not in valid_categories:
        category = "Personal"

    try:
        loan = Loan(
            user_id=current_user.id,
            loan_id=loan_id,
            loan_name=loan_name.strip(),
            loan_category=category,
            bank_name=bank_name.strip() if bank_name else "Other",
            loan_amount=float(loan_amount),
            interest_rate=float(interest_rate),
            down_payment=float(down_payment) if down_payment else 0.0,
            custom_emi=float(custom_emi) if custom_emi else None,
            start_date=parsed_start_date,
            tenure_months=int(tenure_months),
            notes=notes
        )
        db.session.add(loan)
        db.session.flush()
        
        # Amortize
        rows = generate_amortization(loan)
        for r in rows:
            db.session.add(Schedule(loan_id=loan.id, **r))
            
        update_loan_progress(loan)
        db.session.add(ActivityLog(
            user_id=current_user.id,
            loan_id=loan.id,
            action="CREATE_LOAN",
            detail=f"{loan.loan_id} — {loan.loan_name} (via Chatbot)"
        ))
        db.session.commit()
        return {"success": True, "message": f"Loan '{loan.loan_name}' (ID: {loan.loan_id}) created successfully."}
    except Exception as e:
        db.session.rollback()
        return {"error": f"Failed to create loan: {str(e)}"}


def update_loan_rate(loan_id: str, new_rate: float, effective_date: str = None):
    """Update the annual interest rate of an existing loan by its loan_id.
    Rate should be in % (e.g. 6.5). effective_date (YYYY-MM-DD) is optional, defaults to today.
    """
    loan = Loan.query.filter_by(user_id=current_user.id, loan_id=loan_id.strip()).first()
    if not loan:
        return {"error": f"Loan with ID '{loan_id}' not found."}
        
    try:
        eff_date = datetime.strptime(effective_date, "%Y-%m-%d").date() if effective_date else date.today()
    except ValueError:
        return {"error": "Invalid effective_date format. Must be YYYY-MM-DD."}
        
    try:
        old_rate = loan.interest_rate
        recalc_unpaid_with_new_rate(loan, float(new_rate), eff_date)
        loan.interest_rate = float(new_rate)
        
        db.session.add(LoanAuditLog(loan_id=loan.id, field="interest_rate", old_value=str(old_rate), new_value=str(new_rate)))
        update_loan_progress(loan)
        db.session.add(ActivityLog(
            user_id=current_user.id,
            loan_id=loan.id,
            action="RECALC",
            detail=f"Rate changed to {new_rate}% (via Chatbot)"
        ))
        db.session.commit()
        return {"success": True, "message": f"Interest rate for loan '{loan.loan_name}' updated to {new_rate}%."}
    except Exception as e:
        db.session.rollback()
        return {"error": f"Failed to update interest rate: {str(e)}"}


def update_loan_tenure(loan_id: str, new_tenure_months: int):
    """Update the total remaining tenure (in months) of an unpaid loan.
    This will adjust the remaining installments.
    """
    from dateutil.relativedelta import relativedelta
    loan = Loan.query.filter_by(user_id=current_user.id, loan_id=loan_id.strip()).first()
    if not loan:
        return {"error": f"Loan with ID '{loan_id}' not found."}
        
    try:
        old_tenure = loan.tenure_months
        unpaid = sorted([s for s in loan.schedules if s.payment_status != "Paid"], key=lambda x: x.month_index)
        if not unpaid:
            return {"error": "No unpaid installments remaining to adjust tenure."}
            
        remaining = loan.remaining_balance
        monthly_rate = (loan.interest_rate / 100.0) / 12.0
        new_emi = emi_amount(remaining, loan.interest_rate, int(new_tenure_months))
        
        start_date = unpaid[0].payment_date
        start_idx = unpaid[0].month_index - 1
        
        for s in unpaid:
            db.session.delete(s)
        db.session.flush()
        
        rem = remaining
        for i in range(1, int(new_tenure_months) + 1):
            interest = max(round(rem * monthly_rate, 2), 0.0)
            principal = round(new_emi - interest, 2)
            if i == int(new_tenure_months) or principal >= rem:
                principal = round(rem, 2)
                emi = round(principal + interest, 2)
                rem = 0.0
                pay_date = start_date + relativedelta(months=i-1)
                db.session.add(Schedule(
                    loan_id=loan.id,
                    month_index=start_idx + i,
                    payment_date=pay_date,
                    emi=emi,
                    principal=principal,
                    interest=interest,
                    remaining_balance=0.0,
                    is_revised=True
                ))
                break
            else:
                emi = new_emi
            rem = max(round(rem - principal, 2), 0.0)
            pay_date = start_date + relativedelta(months=i-1)
            db.session.add(Schedule(
                loan_id=loan.id,
                month_index=start_idx + i,
                payment_date=pay_date,
                emi=emi,
                principal=principal,
                interest=interest,
                remaining_balance=rem,
                is_revised=True
            ))
                                    
        loan.tenure_months = start_idx + int(new_tenure_months)
        db.session.add(LoanAuditLog(loan_id=loan.id, field="tenure_months", old_value=str(old_tenure), new_value=str(loan.tenure_months)))
        update_loan_progress(loan)
        db.session.add(ActivityLog(
            user_id=current_user.id,
            loan_id=loan.id,
            action="RECALC",
            detail=f"Tenure adjusted to {new_tenure_months} unpaid months (via Chatbot)"
        ))
        db.session.commit()
        return {"success": True, "message": f"Tenure for loan '{loan.loan_name}' updated. Remaining unpaid tenure set to {new_tenure_months} months."}
    except Exception as e:
        db.session.rollback()
        return {"error": f"Failed to update tenure: {str(e)}"}


def update_loan_metadata(loan_id: str, field: str, value: str):
    """Update metadata fields of a loan, such as: 'loan_name', 'bank_name', 'loan_category', 'notes'."""
    loan = Loan.query.filter_by(user_id=current_user.id, loan_id=loan_id.strip()).first()
    if not loan:
        return {"error": f"Loan with ID '{loan_id}' not found."}
        
    valid_fields = ["loan_name", "bank_name", "loan_category", "notes"]
    field = field.strip().lower()
    if field not in valid_fields:
        return {"error": f"Field '{field}' is immutable or invalid. You can only update: {', '.join(valid_fields)}"}
        
    try:
        old_val = getattr(loan, field)
        new_val = value.strip()
        
        if field == "loan_category":
            valid_categories = ["Home", "Auto", "Personal", "Education", "Business", "Gold", "Other"]
            new_val = new_val.title()
            if new_val not in valid_categories:
                return {"error": f"Invalid category. Must be one of: {', '.join(valid_categories)}"}
                
        setattr(loan, field, new_val)
        db.session.add(LoanAuditLog(loan_id=loan.id, field=field, old_value=str(old_val), new_value=str(new_val)))
        db.session.add(ActivityLog(
            user_id=current_user.id,
            loan_id=loan.id,
            action="EDIT_LOAN",
            detail=f"{field} updated via Chatbot"
        ))
        db.session.commit()
        return {"success": True, "message": f"Updated {field} to '{new_val}' for loan '{loan.loan_name}'."}
    except Exception as e:
        db.session.rollback()
        return {"error": f"Failed to update metadata: {str(e)}"}


SYSTEM_INSTRUCTION = """
You are the LoanLedger AI Assistant. You help users manage their loans.
You can list loans, show details, create new loans, change rates, tenures, and other details.

When creating a loan:
- You need the loan ID, loan name, bank name, amount, interest rate, tenure (in months), and start date (YYYY-MM-DD).
- Try to extract these details. If the user does not specify a field, use these guidelines:
  - Loan ID: Generate a unique, short, identifier (e.g. lowercase with hyphens, like 'auto-2025' or 'home-refinance').
  - Start date: Use today's date if not specified.
  - Loan category: Infer from name (e.g., 'car loan' -> Auto) or use 'Personal' as default.
  - Bank/Lender: Use 'Other' if not specified.
- If vital parameters (like amount, rate, or tenure) are missing or unclear, ask the user for them before calling the create_loan tool.
- Confirm the parameters with the user when calling the tool.

When updating a loan:
- The user must specify the loan ID. If they don't, ask which loan they want to update.
- If they want to change the interest rate, call `update_loan_rate`.
- If they want to change the tenure, call `update_loan_tenure`.
- If they want to change other details (name, bank, notes, category), call `update_loan_metadata`.
- If a tool returns an error (e.g. duplicate loan ID or non-existent loan ID), explain the error to the user politely.

Always keep your tone professional, helpful, and concise.
"""

@chatbot_bp.route("/chat", methods=["POST"])
@login_required
def chat():
    # 1. Resolve Gemini API Key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        # Check settings database
        setting_rec = Setting.query.filter_by(user_id=current_user.id, key="gemini_api_key").first()
        if setting_rec and setting_rec.value:
            api_key = setting_rec.value.strip()

    if not api_key:
        return jsonify({
            "error": "api_key_missing",
            "reply": "Hi! I'm your LoanLedger Assistant. To start using me, please configure your **Gemini API Key** in your **Settings** panel (Preferences section) or set the `GEMINI_API_KEY` environment variable."
        })

    # 2. Get message and history from request
    req_data = request.get_json() or {}
    message = req_data.get("message", "").strip()
    history_payload = req_data.get("history", [])

    if not message:
        return jsonify({"error": "message_missing", "reply": "Please say something!"})

    try:
        import google.generativeai as genai
    except ImportError:
        return jsonify({
            "error": "library_missing",
            "reply": "The `google-generativeai` Python package is not installed. Please run `pip install google-generativeai` in your terminal to enable the AI chatbot."
        })

    # 3. Configure Gemini client
    try:
        genai.configure(api_key=api_key)
        
        # Define tools
        tools = [list_loans, get_loan_details, create_loan, update_loan_rate, update_loan_tenure, update_loan_metadata]
        
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            tools=tools,
            system_instruction=SYSTEM_INSTRUCTION
        )

        # Reconstruct chat history in the format expected by google-generativeai
        contents = []
        for turn in history_payload:
            role = turn.get("role")
            parts = turn.get("parts")
            if role and parts:
                text_parts = []
                for p in parts:
                    if isinstance(p, dict) and "text" in p:
                        text_parts.append(p["text"])
                    elif isinstance(p, str):
                        text_parts.append(p)
                if text_parts:
                    contents.append({
                        "role": "user" if role == "user" else "model",
                        "parts": text_parts
                    })

        # Start chat session
        chat_session = model.start_chat(history=contents, enable_automatic_function_calling=True)
        response = chat_session.send_message(message)

        # Format history to return to frontend
        updated_history = []
        for content in chat_session.history:
            parts = []
            for part in content.parts:
                # If part has text, save it
                if hasattr(part, "text") and part.text:
                    parts.append({"text": part.text})
                # We skip function call/response structures to keep frontend payload simple
            if parts:
                updated_history.append({
                    "role": content.role,
                    "parts": parts
                })

        return jsonify({
            "reply": response.text,
            "history": updated_history
        })

    except Exception as e:
        return jsonify({
            "error": "gemini_error",
            "reply": f"An error occurred while communicating with Gemini: {str(e)}"
        })
