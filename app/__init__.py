import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from datetime import datetime

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object("app.config.Config")

    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), "instance"), exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    from app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.blueprints.auth import auth_bp
    from app.blueprints.dashboard import dashboard_bp
    from app.blueprints.loans import loans_bp
    from app.blueprints.schedule import schedule_bp
    from app.blueprints.recalculate import recalc_bp
    from app.blueprints.reports import reports_bp
    from app.blueprints.settings import settings_bp
    from app.blueprints.api import api_bp
    from app.blueprints.chatbot import chatbot_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(loans_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(recalc_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(chatbot_bp)

    from app.utils import format_currency, format_date
    app.jinja_env.filters["money"] = format_currency
    app.jinja_env.filters["fdate"] = format_date

    @app.context_processor
    def inject_globals():
        return {"now": datetime.utcnow()}

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template("errors/404.html"), 404

    @app.after_request
    def set_cache_headers(response):
        if current_user.is_authenticated:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    with app.app_context():
        db.create_all()

    return app
