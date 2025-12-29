# =============================================================================
# app/models/user.py - Modelo de usuario
#
# Clase User con autenticación segura y roles.
# Usa la instancia global de db desde extensions.py
# =============================================================================

from app.extensions import db
from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model):
    """Modelo de usuario con autenticación y roles (admin/user)."""
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default="user")

    def set_password(self, password):
        """Establece la contraseña hasheada (método seguro)."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verifica si la contraseña coincide (usado en login)."""
        return check_password_hash(self.password_hash, password)