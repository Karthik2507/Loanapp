from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from app.blueprints.dashboard import _stats, _charts

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/me")
@login_required
def me():
    return jsonify({
        "id": current_user.id, "username": current_user.username,
        "full_name": current_user.full_name, "currency": current_user.preferred_currency,
    })


@api_bp.route("/dashboard")
@login_required
def dashboard():
    loans = current_user.loans.filter_by(is_archived=False).all()
    return jsonify({"stats": _stats(loans), "charts": _charts(loans)})
