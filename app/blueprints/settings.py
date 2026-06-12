from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user, logout_user
from app import db
from app.models import User, ActivityLog
from app.forms import ProfileForm, PreferencesForm, ChangePasswordForm

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


@settings_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    from app.models import Setting
    profile_form = ProfileForm(obj=current_user)
    pref_form = PreferencesForm(obj=current_user)
    
    # Populate API key from Setting table
    api_key_setting = Setting.query.filter_by(user_id=current_user.id, key="gemini_api_key").first()
    if api_key_setting:
        pref_form.gemini_api_key.data = api_key_setting.value

    # Populate monthly income from Setting table
    income_setting = Setting.query.filter_by(user_id=current_user.id, key="monthly_income").first()
    if income_setting:
        pref_form.monthly_income.data = float(income_setting.value) if income_setting.value else 0.0
        
    pwd_form = ChangePasswordForm()
    return render_template("settings/index.html",
                           profile_form=profile_form, pref_form=pref_form, pwd_form=pwd_form)


@settings_bp.route("/profile", methods=["POST"])
@login_required
def update_profile():
    form = ProfileForm()
    if form.validate_on_submit():
        # uniqueness check
        existing = User.query.filter(((User.username == form.username.data) | (User.email == form.email.data.lower())) & (User.id != current_user.id)).first()
        if existing:
            flash("Username or email already in use.", "danger")
            return redirect(url_for("settings.index"))
        current_user.full_name = form.full_name.data
        current_user.username = form.username.data
        current_user.email = form.email.data.lower()
        db.session.add(ActivityLog(user_id=current_user.id, action="UPDATE_PROFILE", detail="Profile updated"))
        db.session.commit()
        flash("Profile updated.", "success")
    else:
        flash("Please correct the errors and resubmit.", "danger")
    return redirect(url_for("settings.index"))


@settings_bp.route("/preferences", methods=["POST"])
@login_required
def update_preferences():
    from app.models import Setting
    form = PreferencesForm()
    if form.validate_on_submit():
        current_user.preferred_currency = form.preferred_currency.data
        current_user.preferred_date_format = form.preferred_date_format.data
        
        # Save or update Gemini API key in Setting table
        api_key_setting = Setting.query.filter_by(user_id=current_user.id, key="gemini_api_key").first()
        new_key_value = form.gemini_api_key.data.strip() if form.gemini_api_key.data else ""
        if api_key_setting:
            if new_key_value:
                api_key_setting.value = new_key_value
            else:
                db.session.delete(api_key_setting)
        elif new_key_value:
            db.session.add(Setting(user_id=current_user.id, key="gemini_api_key", value=new_key_value))

        # Save or update Monthly Income in Setting table
        income_setting = Setting.query.filter_by(user_id=current_user.id, key="monthly_income").first()
        new_income_value = str(form.monthly_income.data) if form.monthly_income.data is not None else ""
        if income_setting:
            if new_income_value:
                income_setting.value = new_income_value
            else:
                db.session.delete(income_setting)
        elif new_income_value:
            db.session.add(Setting(user_id=current_user.id, key="monthly_income", value=new_income_value))
            
        db.session.commit()
        flash("Preferences saved.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/password", methods=["POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Current password is incorrect.", "danger")
            return redirect(url_for("settings.index"))
        current_user.set_password(form.new_password.data)
        db.session.add(ActivityLog(user_id=current_user.id, action="CHANGE_PASSWORD", detail="Password changed"))
        db.session.commit()
        logout_user()
        flash("Password changed. Please log in again to verify.", "success")
        return redirect(url_for("auth.login"))
    else:
        flash("Please correct the errors.", "danger")
    return redirect(url_for("settings.index"))
