from flask import Blueprint, render_template, request, redirect, url_for
from werkzeug.security import generate_password_hash

from app.decorators import require_admin
from app.extensions import db
from app.models.user import User
from app.utils.logging import get_logger


logger = get_logger(__name__)

users_bp = Blueprint("users", __name__)


def _users_page(error=None):
    return render_template(
        "users.html",
        users=User.query.order_by(User.username.asc()).all(),
        error=error,
    )


@users_bp.route("/users", methods=["GET", "POST"])
@require_admin
def users():
    """Pagina principal de gestion de usuarios."""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        role = (request.form.get("role") or "").strip().lower()

        if not username or not password or not role:
            return _users_page("Todos los campos son obligatorios")
        if len(username) < 4:
            return _users_page("El nombre de usuario debe tener al menos 4 caracteres")
        if len(password) < 8:
            return _users_page("La contrasena debe tener al menos 8 caracteres")
        if role not in ["admin", "user"]:
            return _users_page("Rol invalido (solo admin o user)")
        if User.query.filter_by(username=username).first():
            return _users_page("El nombre de usuario ya existe")

        new_user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role=role,
        )
        db.session.add(new_user)
        db.session.commit()
        logger.info("Usuario creado exitosamente: %s (rol: %s)", username, role)
        return redirect(url_for("users.users"))

    return _users_page()


@users_bp.route("/users/change_role/<int:u_id>", methods=["POST"])
@require_admin
def change_user_role(u_id):
    """Cambia el rol de un usuario existente."""
    user = User.query.get_or_404(u_id)
    new_role = (request.form.get("role") or "").strip().lower()
    if new_role in ["admin", "user"]:
        old_role = user.role
        user.role = new_role
        db.session.commit()
        logger.info("Rol cambiado para usuario %s: %s -> %s", user.username, old_role, new_role)
    else:
        logger.warning("Intento de rol invalido para usuario %s: %s", u_id, new_role)
    return redirect(url_for("users.users"))


@users_bp.route("/users/delete/<int:u_id>", methods=["POST"])
@require_admin
def delete_user(u_id):
    """Elimina un usuario, excepto el admin principal."""
    user = User.query.get_or_404(u_id)
    if user.username == "admin":
        logger.warning("Intento de eliminar usuario admin bloqueado")
        return redirect(url_for("users.users"))
    username = user.username
    db.session.delete(user)
    db.session.commit()
    logger.info("Usuario eliminado: %s", username)
    return redirect(url_for("users.users"))
