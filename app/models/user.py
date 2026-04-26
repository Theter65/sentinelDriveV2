# =============================================================================
# app/models/user.py - Modelo de usuario
#
# Clase User con autenticación segura y roles.
# Usa la instancia global de db desde extensions.py
# =============================================================================

from app.extensions import db
import bcrypt
from werkzeug.security import check_password_hash

class User(db.Model):
    """Modelo de usuario con autenticación y roles (admin/user)."""
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default="user")

    def set_password(self, password):
        """Establece la contraseña hasheada con bcrypt."""
        password_bytes = password.encode("utf-8")
        self.password_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")

    def check_password(self, password):
        """Verifica bcrypt y conserva compatibilidad con hashes previos."""
        if not self.password_hash:
            return False
        if self.password_hash.startswith("$2"):
            return bcrypt.checkpw(password.encode("utf-8"), self.password_hash.encode("utf-8"))
        return check_password_hash(self.password_hash, password)
