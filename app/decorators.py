"""Decoradores de seguridad para rutas autenticadas y administrativas."""

from functools import wraps

from flask import redirect, session, url_for

from app.models.user import User
from app.utils.logging import get_logger


logger = get_logger(__name__)


def login_required(f):
    """Requiere que el usuario este autenticado."""

    @wraps(f)
    def decorated(*args, **kwargs):
        """Valida sesion activa antes de ejecutar la vista protegida."""
        username = session.get("user")
        if not username:
            return redirect(url_for("auth.login"))

        user = User.query.filter_by(username=username).first()
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
        """Valida sesion y rol administrativo antes de ejecutar la vista."""
        username = session.get("user")
        if not username:
            return redirect(url_for("auth.login"))

        user = User.query.filter_by(username=username).first()
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
