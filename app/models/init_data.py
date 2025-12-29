from app.extensions import db
from app.models.user import User
from werkzeug.security import generate_password_hash
from app.utils.logging import get_logger

logger = get_logger(__name__)

def initialize_database():
    """Inicializa datos base: usuario admin (solo si no existe)."""
    admin_user = User.query.filter_by(username="admin").first()
    if not admin_user:
        admin_user = User(
            username="admin",
            password_hash=generate_password_hash("admin123"),  # ¡CAMBIAR YA!
            role="admin"
        )
        db.session.add(admin_user)
        db.session.commit()
        logger.info("Usuario admin creado: admin / admin123 (role='admin')")
    elif admin_user.role != "admin":
        admin_user.role = "admin"
        db.session.commit()
        logger.info("Rol de admin corregido a 'admin'")