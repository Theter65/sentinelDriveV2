from flask import Blueprint, render_template, request, redirect, url_for, session

from app.decorators import login_required
from app.models.user import User
from app.utils.logging import get_logger


logger = get_logger(__name__)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/", methods=["GET", "POST"])
def login():
    """Pagina de inicio de sesion."""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session.clear()
            session["user"] = user.username
            session["role"] = user.role.lower()
            session.permanent = True
            logger.info("Login exitoso: %s (role=%s)", username, session["role"])
            return redirect(url_for("dashboard.dashboard"))
        logger.warning("Intento de login fallido para usuario: %s", username or "<vacio>")
        return render_template("login.html", error="Credenciales incorrectas")
    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Cerrar sesion y limpiar datos de sesion."""
    username = session.get("user")
    logger.info("Logout exitoso: %s", username)
    session.clear()
    return redirect(url_for("auth.login"))
