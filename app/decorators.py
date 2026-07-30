# app/decorators.py - Decoradores de seguridad para rutas
#
# Proporciona decoradores para control de acceso:
# - login_required: requiere sesión activa
# - require_admin: requiere sesión activa + rol admin
# Ambos redirigen al login si la validación falla.
# =============================================================================

from functools import wraps

from flask import redirect, session, url_for
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.init_data import ensure_database_schema
from app.models.user import User
from app.utils.logging import get_logger


logger = get_logger(__name__)


def _fetch_user_by_username(username: str):
    """Obtiene un usuario y reintenta si faltara una tabla del esquema."""
    if not ensure_database_schema():
        return None

    try:
        return User.query.filter_by(username=username).first()
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.warning("Esquema de usuarios incompleto; reintentando recreacion: %s", exc)
        if not ensure_database_schema():
            return None
        return User.query.filter_by(username=username).first()


def login_required(f):
    """Requiere que el usuario esté autenticado."""

    @wraps(f)
    def decorated(*args, **kwargs):
        """Valida sesion activa antes de ejecutar la vista protegida."""
        username = session.get("user")
        if not username:
            return redirect(url_for("auth.login"))

        user = _fetch_user_by_username(username)
        if not user:
            logger.warning("Sesion invalida detectada para usuario inexistente: %s", username)
            session.clear()
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated


def require_admin(f):
    """Requiere que el usuario tenga rol admin."""

    @wraps(f)
    def decorated(*args, **kwargs):
        """Valida sesión y rol administrativo antes de ejecutar la vista."""
        username = session.get("user")
        if not username:
            return redirect(url_for("auth.login"))

        user = _fetch_user_by_username(username)
        if not user:
            logger.warning("Sesion admin invalida para usuario inexistente: %s", username)
            session.clear()
            return redirect(url_for("auth.login"))

        if user.role.lower() != "admin":
            logger.warning("Acceso denegado a ruta admin para usuario %s", username)
            return redirect(url_for("dashboard.dashboard"))

        session["role"] = user.role.lower()
        return f(*args, **kwargs)

    return decorated
