import csv
import io
from flask import Blueprint, render_template, request, Response, abort
from flask_login import login_required, current_user
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from app.models import Loan

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("/")
@login_required
def index():
    from datetime import date
    from app.models import Schedule
    
    loans = current_user.loans.filter_by(is_archived=False).all()
    total_borrowed = sum(l.loan_amount for l in loans)
    total_remaining = sum(l.remaining_balance for l in loans)
    total_interest = sum(s.interest for l in loans for s in l.schedules)
    balloons = [l for l in loans if l.balloon_date]
    closures = [l for l in loans if l.loan_status == "Completed"]
    
    # 1. Exposure Risk data (active outstanding balance by bank)
    by_bank = {}
    for l in loans:
        if l.loan_status != "Completed":
            by_bank[l.bank_name] = by_bank.get(l.bank_name, 0.0) + (l.remaining_balance or 0.0)
            
    # 2. Fiscal Year choices based on oldest loan start date
    oldest_loan = current_user.loans.order_by(Loan.start_date.asc()).first()
    start_year = oldest_loan.start_date.year if oldest_loan else date.today().year
    current_year = date.today().year
    
    fy_choices = []
    for y in range(start_year - 1, current_year + 1):
        fy_choices.append({
            "val": y,
            "label": f"FY {y}-{str(y+1)[2:]} (Apr {y} - Mar {y+1})"
        })
        
    # 3. Dynamic Fiscal Year Tax Summary Report
    selected_fy = request.args.get("fy", type=int)
    fy_data = None
    if selected_fy:
        fy_start = date(selected_fy, 4, 1)
        fy_end = date(selected_fy + 1, 3, 31)
        
        fy_data = {
            "label": f"FY {selected_fy}-{str(selected_fy+1)[2:]}",
            "loans": [],
            "total_principal": 0.0,
            "total_interest": 0.0,
            "total_paid": 0.0
        }
        for l in loans:
            # query paid schedules in date range
            paid_installments = l.schedules.filter(
                Schedule.payment_status == "Paid",
                Schedule.paid_date >= fy_start,
                Schedule.paid_date <= fy_end
            ).all()
            if paid_installments:
                p_sum = sum(s.principal for s in paid_installments)
                i_sum = sum(s.interest for s in paid_installments)
                tot = sum(s.emi for s in paid_installments)
                fy_data["loans"].append({
                    "loan_id": l.loan_id,
                    "loan_name": l.loan_name,
                    "principal": round(p_sum, 2),
                    "interest": round(i_sum, 2),
                    "total": round(tot, 2)
                })
                fy_data["total_principal"] += p_sum
                fy_data["total_interest"] += i_sum
                fy_data["total_paid"] += tot
                
        # round sums
        fy_data["total_principal"] = round(fy_data["total_principal"], 2)
        fy_data["total_interest"] = round(fy_data["total_interest"], 2)
        fy_data["total_paid"] = round(fy_data["total_paid"], 2)
        
    return render_template("reports/index.html", loans=loans,
                           total_borrowed=total_borrowed, total_remaining=total_remaining,
                           total_interest=total_interest, balloons=balloons, closures=closures,
                           by_bank=by_bank, fy_choices=fy_choices, selected_fy=selected_fy, fy_data=fy_data)


@reports_bp.route("/export.csv")
@login_required
def export_csv():
    loans = current_user.loans.all()
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["Loan ID", "Name", "Category", "Bank", "Amount", "Rate %", "Tenure",
                "Start", "Status", "Down Payment","Remaining", "Completion %", "Closed At"])
    for l in loans:
        w.writerow([l.loan_id, l.loan_name, l.loan_category, l.bank_name, f"{l.loan_amount:.2f}",
                    f"{l.interest_rate:.2f}", l.tenure_months, l.start_date.isoformat(),
                    l.loan_status, l.down_payment, f"{l.remaining_balance:.2f}", f"{l.completion_percentage:.2f}",
                    l.closed_at.isoformat() if l.closed_at else ""])
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=loans.csv"})


@reports_bp.route("/export.pdf")
@login_required
def export_pdf():
    loans = current_user.loans.all()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=24, bottomMargin=24, leftMargin=24, rightMargin=24)
    styles = getSampleStyleSheet()
    elems = [Paragraph("Loan Portfolio Report", styles["Title"]), Spacer(1, 12)]
    data = [["Loan ID", "Name", "Category", "Bank", "Amount", "Rate %", "Tenure",
             "Status", "Down Payment","Remaining", "Completion %"]]
    for l in loans:
        data.append([l.loan_id, l.loan_name, l.loan_category, l.bank_name,
                     f"{l.loan_amount:,.2f}", f"{l.interest_rate:.2f}", l.tenure_months,
                     l.loan_status, l.down_payment, f"{l.remaining_balance:,.2f}", f"{l.completion_percentage:.1f}%"])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E40AF")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
    ]))
    elems.append(t)
    doc.build(elems)
    buf.seek(0)
    return Response(buf.getvalue(), mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=loan_report.pdf"})


@reports_bp.route("/print")
@login_required
def print_view():
    loans = current_user.loans.all()
    return render_template("reports/print.html", loans=loans)
