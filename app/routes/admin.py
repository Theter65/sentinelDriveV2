from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.decorators import require_admin
from app.extensions import db
from app.models.event import Event
from app.models.location import Location
from app.models.user import User
from app.utils.logging import get_logger


logger = get_logger(__name__)

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin")
@require_admin
def admin_panel():
    total_events = Event.query.count()
    total_locations = Location.query.count()
    return render_template(
        "admin.html",
        total_events=total_events,
        total_locations=total_locations,
    )


@admin_bp.route("/admin/purge_history", methods=["POST"])
@require_admin
def purge_history():
    """Borra TODO el historial de Location y Event (solo admin) con re-autenticacion.

    Seguridad:
    - Requiere rol admin.
    - Requiere re-ingresar la contrasena del usuario admin actual.
    - Accion auditada (usuario, IP, timestamp) via logs.
    """
    username = session.get("user")
    password = request.form.get("password") or ""

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        flash("Contrasena incorrecta. No se realizo el borrado.", "danger")
        logger.warning("AUDIT purge_history denied user=%s ip=%s", username, _client_ip())
        return redirect(url_for("dashboard.dashboard"))

    try:
        # Flask-SQLAlchemy inicia transacciones implicitamente; no usamos session.begin()
        # para evitar "A transaction is already begun on this Session".
        db.session.query(Location).delete(synchronize_session=False)
        db.session.query(Event).delete(synchronize_session=False)
        db.session.commit()
        flash("Historial borrado: ubicaciones (GPS) y eventos eliminados correctamente.", "success")
        logger.warning("AUDIT purge_history success user=%s ip=%s", username, _client_ip())
    except Exception as exc:
        db.session.rollback()
        flash("Error al borrar historial. Revisa logs del servidor.", "danger")
        logger.error("AUDIT purge_history error user=%s ip=%s err=%s", username, _client_ip(), exc, exc_info=True)

    return redirect(url_for("dashboard.dashboard"))


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"
