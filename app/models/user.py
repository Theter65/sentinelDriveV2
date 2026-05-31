# app/models/user.py - Modelo de usuarios y autenticación
#
# Gestiona cuentas de usuario con roles (admin/operador).
# Usa bcrypt para hashing de contraseñas con compatibilidad
# hacia atrás con hashes generados por werkzeug.
# =============================================================================

from app.extensions import db
import bcrypt
from werkzeug.security import check_password_hash

class User(db.Model):
    """Modelo de usuario con autenticación y roles (admin/user)."""

    __tablename__ = 'user'

    # Identificador único
    id = db.Column(db.Integer, primary_key=True)

    # Nombre de usuario (único, obligatorio)
    username = db.Column(db.String(50), unique=True, nullable=False)

    # Hash de contraseña (bcrypt, almacenado como string)
    password_hash = db.Column(db.String(128), nullable=False)

    # Rol del usuario: admin | user
    role = db.Column(db.String(20), default="user")

    def set_password(self, password):
        """Genera hash bcrypt de la contraseña."""
        password_bytes = password.encode("utf-8")
        self.password_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")

    def check_password(self, password):
        """Verifica contraseña contra bcrypt o hash legacy de werkzeug."""
        if not self.password_hash:
            return False
        if self.password_hash.startswith("$2"):
            return bcrypt.checkpw(password.encode("utf-8"), self.password_hash.encode("utf-8"))
        return check_password_hash(self.password_hash, password)
