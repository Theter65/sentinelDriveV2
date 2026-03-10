from functools import wraps

from flask import redirect, session, url_for

from app.utils.logging import get_logger


logger = get_logger(__name__)


def login_required(f):
    """Requiere que el usuario este autenticado."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated


def require_admin(f):
    """Requiere que el usuario tenga rol admin."""

    @wraps(f)
    def decorated(*args, **kwargs):
        user = session.get("user")
        if not user or session.get("role") != "admin":
            logger.warning("Acceso denegado a ruta admin para usuario %s", user)
            return redirect(url_for("dashboard.dashboard"))
        return f(*args, **kwargs)

    return decorated
