from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash
from app.models.user import User
from app.decorators import login_required
from app.utils.logging import get_logger

logger = get_logger(__name__)

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/", methods=["GET", "POST"])
def login():
    """Página de inicio de sesión con autenticación segura."""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session["user"] = user.username
            session["role"] = user.role.lower()
            logger.info(f"Login exitoso: {username} (role={session['role']})")
            return redirect(url_for("dashboard.dashboard"))
        logger.warning(f"Intento de login fallido para usuario: {username}")
        return render_template("login.html", error="Credenciales incorrectas")
    return render_template("login.html")

@auth_bp.route("/logout")
@login_required
def logout():
    """Cerrar sesión y limpiar datos de sesión."""
    username = session.get("user")
    logger.info(f"Logout exitoso: {username}")
    session.clear()
    return redirect(url_for("auth.login"))