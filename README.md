# LoanLedger — Flask Loan Amortization & Management SaaS

Production-grade Flask app for managing loans, generating amortization
schedules, applying mid-loan interest revisions, handling balloon
payments, recalculating EMIs, and producing executive dashboards and
reports. Designed to look and feel like a modern fintech platform
(Stripe / Mercury / Ramp).

## Tech stack

- **Backend**: Python 3.10+, Flask 3, Flask Blueprints, Flask-Login,
  Flask-WTF, WTForms, SQLAlchemy ORM
- **Database**: SQLite3 (file-based, no setup)
- **Frontend**: HTML5 + CSS3 + vanilla JavaScript + Jinja2 templates
- **Charts**: Chart.js (CDN)
- **Icons**: Lucide (CDN)
- **PDF/CSV**: ReportLab + Python `csv`

No build step. No Node. No Docker required.

## Quick start

```bash
# 1. Create a virtualenv (recommended)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Initialize the database + load demo data (one command)
export FLASK_APP=run.py             # Windows (cmd): set FLASK_APP=run.py
flask seed

# 4. Run
python run.py
# -> http://localhost:5000
```

Demo login created by `flask seed`:
- Username: `demo`
- Password: `Demo@1234`

If you only want an empty DB (no demo data) use `flask init-db`.

## Project structure

```
loanapp/
├── run.py                  # Entry point + CLI commands
├── requirements.txt
├── README.md
├── instance/
│   └── loanledger.sqlite3  # Created on first run
└── app/
    ├── __init__.py         # App factory
    ├── config.py
    ├── models.py           # All SQLAlchemy models
    ├── forms.py            # WTForms
    ├── utils.py            # Currency, amortization engine, helpers
    ├── seed.py             # Demo data
    ├── blueprints/
    │   ├── auth.py         # Register / Login / Logout
    │   ├── dashboard.py    # KPIs + analytics
    │   ├── loans.py        # CRUD + details + archive
    │   ├── schedule.py     # Amortization schedule + mark paid
    │   ├── recalculate.py  # EMI / rate / tenure / lump-sum
    │   ├── reports.py      # PDF + CSV exports
    │   ├── settings.py     # Profile + preferences + password
    │   └── api.py          # AJAX endpoints (JSON)
    ├── templates/          # Jinja2 templates
    └── static/             # CSS + JS + images
```

## Features implemented

**Authentication**
- Register, login (username OR email), logout
- Password hashing (Werkzeug)
- CSRF protection on every form (Flask-WTF)
- SQLAlchemy ORM (parameterized queries — no SQL injection)
- Session-based auth (Flask-Login), protected routes

**Loans**
- Full CRUD + archive (soft delete)
- Manual unique Loan ID, category, bank, amount, rate, down payment,
  start date, tenure, balloon date/amount
- Status: Active, Completed, Overdue, Balloon Pending, Archived

**Amortization engine**
- Generated **once** on loan creation and stored permanently in
  `schedules` table — never regenerated on page load
- Standard EMI formula with monthly compounding
- Balloon loans: final installment auto-absorbs remaining principal +
  interest and closes the loan
- Interest revision: applies only to first unpaid installment onward —
  paid installments are immutable

**Payment management**
- Mark paid / undo paid with notes
- AJAX endpoints update KPI cards, charts, progress, closure eligibility
  without page reload
- Activity + audit logs are immutable

**Recalculation module**
- EMI recalculation, interest change, tenure change, extra payment,
  lump sum, early-payoff simulation
- Only unpaid installments are touched

**Dashboard analytics**
- 8 KPI cards (total loan, interest payable, active, completed, closed
  this month, remaining balance, total paid, outstanding)
- Portfolio Health Score (0–100)
- Loan distribution doughnut (by bank/category/status)
- Cash-flow projection line (3 / 6 / 12 months)
- Debt-reduction area chart
- Interest burden stacked bar
- Balloon risk widget
- Loan-completion forecast timeline
- Smart insights panel

**Reports**
- Loan summary, remaining balance, balloon, interest revision,
  early-payoff, closure reports
- Export to **PDF** (ReportLab), **CSV**, and Print view

**Settings**
- Profile (name / username / email), change password, preferred
  currency (₹, $, €, £, ¥), preferred date format

**UI/UX**
- Sticky sidebar, sticky top nav, fixed Logout at bottom
- Quick "Add Loan" button on every page except Settings
- Responsive (mobile + desktop), smooth animations
- Modern cards, soft shadows, rounded corners
- Empty states, loading states, confirmation modals
- 60-30-10 palette: white / banking blue / emerald accent
- NO dark mode / theme switcher (per spec)

## Notes

- Database file lives in `instance/loanledger.sqlite3`. Delete it to
  start over.
- For production, set `SECRET_KEY` via env var and run behind a real
  WSGI server (gunicorn / waitress).
- Backup: copy the `instance/` folder.

## License

MIT — use freely.
