from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, FloatField, IntegerField, DateField, SelectField, TextAreaField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional, Regexp, InputRequired, ValidationError


CURRENCY_CHOICES = [("INR", "₹ INR"), ("USD", "$ USD"), ("EUR", "€ EUR"), ("GBP", "£ GBP"), ("JPY", "¥ JPY")]
DATE_FMT_CHOICES = [("%d %b %Y", "31 Dec 2025"), ("%d/%m/%Y", "31/12/2025"), ("%Y-%m-%d", "2025-12-31"), ("%m/%d/%Y", "12/31/2025")]
CATEGORY_CHOICES = [("Home", "Home"), ("Auto", "Auto"), ("Personal", "Personal"), ("Education", "Education"), ("Business", "Business"), ("Gold", "Gold"), ("Other", "Other")]
STATUS_CHOICES = [("Active", "Active"), ("Completed", "Completed"), ("Overdue", "Overdue"), ("Balloon Pending", "Balloon Pending"), ("Archived", "Archived")]
MONTH_CHOICES = [
    ("1", "January"), ("2", "February"), ("3", "March"), ("4", "April"),
    ("5", "May"), ("6", "June"), ("7", "July"), ("8", "August"),
    ("9", "September"), ("10", "October"), ("11", "November"), ("12", "December")
]
REMINDER_DAYS_CHOICES = [
    ("1", "1 day before"),
    ("2", "2 days before"),
    ("3", "3 days before"),
    ("5", "5 days before"),
    ("7", "7 days before"),
    ("10", "10 days before"),
    ("14", "14 days before")
]



class RegisterForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(2, 120)])
    username = StringField("Username", validators=[DataRequired(), Length(3, 64), Regexp(r"^[A-Za-z0-9_.-]+$", message="Letters, numbers, _ . - only")])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=160)])
    password = PasswordField("Password", validators=[DataRequired(), Length(8, 128)])
    confirm = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password", message="Passwords must match")])
    submit = SubmitField("Create account")


class LoginForm(FlaskForm):
    identifier = StringField("Username or Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember me")
    submit = SubmitField("Sign in")


class LoanForm(FlaskForm):
    loan_id = StringField("Loan ID (unique)", validators=[DataRequired(), Length(1, 40)])
    loan_name = StringField("Loan Name", validators=[DataRequired(), Length(1, 120)])
    loan_category = SelectField("Category", choices=CATEGORY_CHOICES, validators=[DataRequired()])
    bank_name = StringField("Bank / Lender", validators=[DataRequired(), Length(1, 120)])
    loan_amount = FloatField("Loan Amount", validators=[DataRequired(), NumberRange(min=0.01)])
    custom_emi = FloatField("Revised Monthly EMI", validators=[Optional(), NumberRange(min=0.01)])
    interest_rate = FloatField("Annual Interest Rate (%)", validators=[InputRequired(), NumberRange(min=0, max=100)])
    down_payment = FloatField("Down Payment", validators=[Optional(), NumberRange(min=0)], default=0)
    start_date = DateField("Start Date", validators=[DataRequired()])
    tenure_months = FloatField("Tenure", validators=[DataRequired(), NumberRange(min=0.01, max=600)])
    tenure_unit = SelectField("Tenure Unit", choices=[("months", "Months"), ("years", "Years")], default="months")
    balloon_date = DateField("Balloon Date", validators=[Optional()])
    balloon_amount = FloatField("Balloon Amount", validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Save Loan")

    def validate_tenure_months(self, field):
        if field.data is not None:
            if self.tenure_unit.data == "months":
                if not field.data.is_integer():
                    raise ValidationError("Tenure in months must be a whole number (no decimals allowed).")
            else:
                months = field.data * 12
                if int(round(months)) < 1:
                    raise ValidationError("Tenure must convert to at least 1 month.")


class MarkPaidForm(FlaskForm):
    schedule_id = IntegerField(validators=[DataRequired()])
    notes = StringField(validators=[Optional(), Length(max=255)])
    submit = SubmitField("Mark Paid")


class InterestRevisionForm(FlaskForm):
    new_rate = FloatField("New Interest Rate (%)", validators=[InputRequired(), NumberRange(min=0, max=100)])
    effective_date = DateField("Effective Date", validators=[DataRequired()])
    submit = SubmitField("Apply Revision")


class RecalcForm(FlaskForm):
    recalc_type = SelectField("Type", choices=[
        ("RATE", "Interest Rate Change"),
        ("TENURE", "Tenure Change"),
        ("EXTRA", "Extra Monthly Payment"),
        ("CLEAR_BALLOON", "Clear Balloon date"),
    ])
    new_rate = FloatField("New Rate (%)", validators=[Optional(), NumberRange(min=0, max=100)])
    new_tenure = IntegerField("New Tenure (months)", validators=[Optional(), NumberRange(min=1, max=600)])
    extra_amount = FloatField("Extra Amount", validators=[Optional(), NumberRange(min=0)])
    effective_date = DateField("Effective Date", validators=[Optional()])
    submit = SubmitField("Recalculate")


class ProfileForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(2, 120)])
    username = StringField("Username", validators=[DataRequired(), Length(3, 64)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Save profile")


class PreferencesForm(FlaskForm):
    preferred_currency = SelectField("Currency", choices=CURRENCY_CHOICES)
    preferred_date_format = SelectField("Date format", choices=DATE_FMT_CHOICES)
    monthly_income = FloatField("Monthly Net Income", validators=[Optional(), NumberRange(min=0)])
    gemini_api_key = StringField("Gemini API Key", validators=[Optional()])
    fy_start_month = SelectField("Fiscal Year Start Month", choices=MONTH_CHOICES, default="4")
    reminders_enabled = BooleanField("Enable System Reminders")
    reminder_days_before = SelectField("Reminder Days Before Due Date", choices=REMINDER_DAYS_CHOICES, default="5")
    reminder_email = StringField("Reminder Destination Email", validators=[Optional(), Email(), Length(max=160)])
    submit = SubmitField("Save preferences")



class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField("New password", validators=[DataRequired(), Length(8, 128)])
    confirm = PasswordField("Confirm new password", validators=[DataRequired(), EqualTo("new_password")])
    submit = SubmitField("Change password")
