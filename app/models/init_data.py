import os
import secrets

from sqlalchemy import text
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models.user import User
from app.utils.logging import get_logger


logger = get_logger(__name__)


def ensure_database_indexes():
    """Create indexes for existing databases without requiring migrations."""
    statements = [
        "CREATE INDEX IF NOT EXISTS ix_event_bus_timestamp ON event (bus_id, timestamp)",
        "CREATE INDEX IF NOT EXISTS ix_location_bus_timestamp ON location (bus_id, timestamp)",
        "CREATE INDEX IF NOT EXISTS ix_maintenance_bus_date ON maintenance (bus_id, date)",
    ]
    for statement in statements:
        db.session.execute(text(statement))
    db.session.commit()


def initialize_database():
    """Inicializa el usuario administrador si no existe."""
    admin_user = User.query.filter_by(username="admin").first()
    if not admin_user:
        admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
        admin_user = User(
            username="admin",
            password_hash=generate_password_hash(admin_password),
            role="admin",
        )
        db.session.add(admin_user)
        db.session.commit()
        logger.warning(
            "Usuario admin creado. Defina DEFAULT_ADMIN_PASSWORD para controlar la clave inicial. Clave temporal: %s",
            admin_password,
        )
    elif admin_user.role != "admin":
        admin_user.role = "admin"
        db.session.commit()
        logger.info("Rol de admin corregido a 'admin'")
