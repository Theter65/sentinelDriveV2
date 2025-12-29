from flask import Blueprint, render_template, request, redirect, url_for
from app.decorators import login_required, require_admin
from app.extensions import db
from app.models.user import User
from werkzeug.security import generate_password_hash
from app.utils.logging import get_logger

logger = get_logger(__name__)

users_bp = Blueprint('users', __name__)

@users_bp.route("/users", methods=["GET", "POST"])
@require_admin
def users():
    """
    Página principal de gestión de usuarios (solo admin).
    - GET: Muestra la lista de usuarios
    - POST: Crea un nuevo usuario
    """
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")

        if not username or not password or not role:
            return render_template("users.html", users=User.query.all(), error="Todos los campos son obligatorios")
        if len(username) < 4:
            return render_template("users.html", users=User.query.all(), error="El nombre de usuario debe tener al menos 4 caracteres")
        if len(password) < 8:
            return render_template("users.html", users=User.query.all(), error="La contraseña debe tener al menos 8 caracteres")
        if role not in ["admin", "user"]:
            return render_template("users.html", users=User.query.all(), error="Rol inválido (solo admin o user)")
        if User.query.filter_by(username=username).first():
            return render_template("users.html", users=User.query.all(), error="El nombre de usuario ya existe")

        new_user = User(
            username=username.strip(),
            password_hash=generate_password_hash(password),
            role=role.lower()
        )
        db.session.add(new_user)
        db.session.commit()
        logger.info(f"Usuario creado exitosamente: {username} (rol: {role})")
        return redirect(url_for("users.users"))

    users_list = User.query.all()
    return render_template("users.html", users=users_list)

@users_bp.route("/users/change_role/<int:u_id>", methods=["POST"])
@require_admin
def change_user_role(u_id):
    """Cambia el rol de un usuario existente (admin/user)."""
    user = User.query.get_or_404(u_id)
    new_role = request.form.get("role")
    if new_role in ["admin", "user"]:
        old_role = user.role
        user.role = new_role.lower()
        db.session.commit()
        logger.info(f"Rol cambiado para usuario {user.username}: {old_role} → {new_role}")
    else:
        logger.warning(f"Intento de rol inválido para usuario {u_id}: {new_role}")
    return redirect(url_for("users.users"))

@users_bp.route("/users/delete/<int:u_id>", methods=["POST"])
@require_admin
def delete_user(u_id):
    """Elimina un usuario (protegido: no permite eliminar admin)."""
    user = User.query.get_or_404(u_id)
    if user.username == "admin":
        logger.warning("Intento de eliminar usuario admin bloqueado")
        return redirect(url_for("users.users"))
    username = user.username
    db.session.delete(user)
    db.session.commit()
    logger.info(f"Usuario eliminado: {username}")
    return redirect(url_for("users.users"))