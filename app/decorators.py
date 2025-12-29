# app/decorators.py
# Decoradores de seguridad reutilizables (login_required, require_admin)

from flask import session, redirect, url_for
from functools import wraps
import logging

logger = logging.getLogger(__name__)

def login_required(f):
    """Requiere que el usuario esté autenticado."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    """Requiere que el usuario tenga rol 'admin'."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = session.get("user")
        if not user or session.get("role") != "admin":
            logger.warning(f"Acceso denegado a ruta admin para usuario {user}")
            return redirect(url_for("dashboard.dashboard"))
        return f(*args, **kwargs)
    return decorated