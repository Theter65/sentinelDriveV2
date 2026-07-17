# app/routes/users.py - Gestión de usuarios y roles
#
# Permite crear, modificar roles, cambiar contraseñas y eliminar
# usuarios del sistema. Incluye protecciones para evitar eliminar
# al último administrador. Solo accesible para rol admin.
# =============================================================================

from flask import Blueprint, flash, render_template, request, redirect, session, url_for

from app.decorators import require_admin
from app.extensions import db
from app.models.user import User
from app.utils.logging import get_logger


logger = get_logger(__name__)

users_bp = Blueprint("users", __name__)


def _admin_count() -> int:
    return User.query.filter_by(role="admin").count()


def _users_page(error=None):
    return render_template(
        "users.html",
        users=User.query.order_by(User.username.asc()).all(),
        error=error,
        admin_user_count=_admin_count(),
        current_username=session.get("user"),
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
            role=role,
        )
        new_user.set_password(password)
        db.session.add(new_user)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Error al crear usuario %s", username)
            return _users_page("Error al crear el usuario")
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
        if user.role == "admin" and new_role != "admin" and _admin_count() <= 1:
            flash("Debe existir al menos un administrador activo en el sistema.", "danger")
            return redirect(url_for("users.users"))
        old_role = user.role
        user.role = new_role
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Error al cambiar rol para usuario %s", user.username)
            flash("Error al cambiar el rol.", "danger")
            return redirect(url_for("users.users"))
        logger.info("Rol cambiado para usuario %s: %s -> %s", user.username, old_role, new_role)
    else:
        logger.warning("Intento de rol invalido para usuario %s: %s", u_id, new_role)
    return redirect(url_for("users.users"))


@users_bp.route("/users/delete/<int:u_id>", methods=["POST"])
@require_admin
def delete_user(u_id):
    """Elimina un usuario, preservando al menos un administrador activo."""
    user = User.query.get_or_404(u_id)
    if user.role == "admin" and _admin_count() <= 1:
        flash("No puedes eliminar al ultimo administrador del sistema.", "danger")
        logger.warning("Intento de eliminar el ultimo administrador bloqueado")
        return redirect(url_for("users.users"))
    username = user.username
    db.session.delete(user)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Error al eliminar usuario %s", username)
        flash("Error al eliminar el usuario.", "danger")
        return redirect(url_for("users.users"))
    logger.info("Usuario eliminado: %s", username)
    return redirect(url_for("users.users"))


@users_bp.route("/users/change_password/<int:u_id>", methods=["POST"])
@require_admin
def change_user_password(u_id):
    """Actualiza la contrasena de un usuario (solo admin)."""
    user = User.query.get_or_404(u_id)
    new_password = request.form.get("new_password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    if len(new_password) < 8:
        flash("La contrasena debe tener al menos 8 caracteres.", "danger")
        return redirect(url_for("users.users"))
    if new_password != confirm_password:
        flash("La confirmacion de contrasena no coincide.", "danger")
        return redirect(url_for("users.users"))

    user.set_password(new_password)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Error al cambiar contrasena para usuario %s", user.username)
        flash("Error al actualizar la contrasena.", "danger")
        return redirect(url_for("users.users"))
    logger.info("Contrasena actualizada para usuario: %s", user.username)
    flash(f"Contrasena actualizada para {user.username}.", "success")
    return redirect(url_for("users.users"))
