import os
import tempfile
import sqlite3
import shutil
from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request, send_file, abort
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

    # Populate fy_start_month from Setting table
    fy_setting = Setting.query.filter_by(user_id=current_user.id, key="fy_start_month").first()
    if fy_setting:
        pref_form.fy_start_month.data = fy_setting.value
    else:
        pref_form.fy_start_month.data = "4"
        
    # Populate reminders_enabled from Setting table
    enabled_setting = Setting.query.filter_by(user_id=current_user.id, key="reminders_enabled").first()
    if enabled_setting:
        pref_form.reminders_enabled.data = enabled_setting.value == "true"
    else:
        pref_form.reminders_enabled.data = False
        
    # Populate reminder_days_before from Setting table
    days_setting = Setting.query.filter_by(user_id=current_user.id, key="reminder_days_before").first()
    if days_setting:
        pref_form.reminder_days_before.data = days_setting.value
    else:
        pref_form.reminder_days_before.data = "5"
        
    # Populate reminder_email from Setting table
    email_setting = Setting.query.filter_by(user_id=current_user.id, key="reminder_email").first()
    if email_setting:
        pref_form.reminder_email.data = email_setting.value
        
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
        
        def set_setting_val(key, val):
            setting = Setting.query.filter_by(user_id=current_user.id, key=key).first()
            if setting:
                if val is not None and str(val).strip() != "":
                    setting.value = str(val).strip()
                else:
                    db.session.delete(setting)
            elif val is not None and str(val).strip() != "":
                db.session.add(Setting(user_id=current_user.id, key=key, value=str(val).strip()))

        set_setting_val("gemini_api_key", form.gemini_api_key.data)
        set_setting_val("monthly_income", form.monthly_income.data if form.monthly_income.data is not None else "")
        set_setting_val("fy_start_month", form.fy_start_month.data)
        set_setting_val("reminders_enabled", "true" if form.reminders_enabled.data else "false")
        set_setting_val("reminder_days_before", form.reminder_days_before.data)
        set_setting_val("reminder_email", form.reminder_email.data)
            
        db.session.commit()
        flash("Preferences saved.", "success")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error in {getattr(form, field).label.text}: {error}", "danger")
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


def verify_sqlite_db(filepath):
    try:
        conn = sqlite3.connect(filepath)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        res = cursor.fetchone()
        if res[0] != "ok":
            conn.close()
            return False
        # verify essential tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        required_tables = ["users", "loans", "schedules", "settings"]
        for t in required_tables:
            if t not in tables:
                conn.close()
                return False
        conn.close()
        return True
    except Exception:
        return False


@settings_bp.route("/backup/download")
@login_required
def download_backup():
    uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
    db_path = uri.replace("sqlite:///", "")
    if not os.path.isabs(db_path):
        db_path = os.path.join(current_app.root_path, db_path)
    if os.path.exists(db_path):
        db.session.remove()
        db.engine.dispose()
        return send_file(db_path, as_attachment=True, download_name="loanledger_backup.sqlite3")
    else:
        abort(404, "Database file not found.")


@settings_bp.route("/backup/restore", methods=["POST"])
@login_required
def restore_backup():
    file = request.files.get("backup_file")
    if not file or file.filename == "":
        flash("No backup file provided.", "danger")
        return redirect(url_for("settings.index"))
        
    if not (file.filename.endswith(".sqlite3") or file.filename.endswith(".db")):
        flash("Invalid file extension. Please upload a .sqlite3 or .db file.", "danger")
        return redirect(url_for("settings.index"))
        
    fd, temp_path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    
    try:
        file.save(temp_path)
        
        if not verify_sqlite_db(temp_path):
            flash("Invalid backup file: integrity check failed or missing schema tables.", "danger")
            os.remove(temp_path)
            return redirect(url_for("settings.index"))
            
        db.session.remove()
        db.engine.dispose()
        
        uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
        db_path = uri.replace("sqlite:///", "")
        if not os.path.isabs(db_path):
            db_path = os.path.join(current_app.root_path, db_path)
            
        backup_path = db_path + ".prev"
        if os.path.exists(db_path):
            shutil.copy2(db_path, backup_path)
            
        try:
            shutil.copy2(temp_path, db_path)
            conn = sqlite3.connect(db_path)
            conn.execute("SELECT count(*) FROM users;")
            conn.close()
            
            os.remove(temp_path)
            if os.path.exists(backup_path):
                os.remove(backup_path)
                
            logout_user()
            flash("Database restored successfully. Please log in with the restored credentials.", "success")
            return redirect(url_for("auth.login"))
            
        except Exception as copy_err:
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, db_path)
                os.remove(backup_path)
            raise copy_err
            
    except Exception as e:
        flash(f"Restore failed: {str(e)}", "danger")
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    return redirect(url_for("settings.index"))

