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
    loans = current_user.loans.filter_by(is_archived=False).all()
    total_borrowed = sum(l.loan_amount for l in loans)
    total_remaining = sum(l.remaining_balance for l in loans)
    total_interest = sum(s.interest for l in loans for s in l.schedules)
    balloons = [l for l in loans if l.balloon_date]
    closures = [l for l in loans if l.loan_status == "Completed"]
    return render_template("reports/index.html", loans=loans,
                           total_borrowed=total_borrowed, total_remaining=total_remaining,
                           total_interest=total_interest, balloons=balloons, closures=closures)


@reports_bp.route("/export.csv")
@login_required
def export_csv():
    loans = current_user.loans.all()
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["Loan ID", "Name", "Category", "Bank", "Amount", "Rate %", "Tenure",
                "Start", "Status", "Remaining", "Completion %", "Closed At"])
    for l in loans:
        w.writerow([l.loan_id, l.loan_name, l.loan_category, l.bank_name, f"{l.loan_amount:.2f}",
                    f"{l.interest_rate:.2f}", l.tenure_months, l.start_date.isoformat(),
                    l.loan_status, f"{l.remaining_balance:.2f}", f"{l.completion_percentage:.2f}",
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
             "Status", "Remaining", "Completion %"]]
    for l in loans:
        data.append([l.loan_id, l.loan_name, l.loan_category, l.bank_name,
                     f"{l.loan_amount:,.2f}", f"{l.interest_rate:.2f}", l.tenure_months,
                     l.loan_status, f"{l.remaining_balance:,.2f}", f"{l.completion_percentage:.1f}%"])
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
