# app/models/init_data.py - Inicialización de base de datos
#
# Rutinas para crear índices compuestos y migraciones ligeras
# de esquema para SQLite y PostgreSQL (sin usar Alembic ni migraciones formales).
# También verifica la existencia del administrador inicial.
# =============================================================================

from sqlalchemy import inspect, text

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

    # Lightweight schema evolution (no Alembic):
    # Add optional columns without breaking existing DBs.
    try:
        dialect = db.engine.dialect.name
        inspector = inspect(db.engine)

        if dialect == "sqlite":
            cols = db.session.execute(text("PRAGMA table_info('bus')")).fetchall()
            col_names = {row[1] for row in cols}
            if "description" not in col_names:
                db.session.execute(text("ALTER TABLE bus ADD COLUMN description TEXT"))
                logger.info("DB: columna agregada bus.description")

            cols = db.session.execute(text("PRAGMA table_info('event')")).fetchall()
            col_names = {row[1] for row in cols}
            if "description" not in col_names:
                db.session.execute(text("ALTER TABLE event ADD COLUMN description TEXT"))
                logger.info("DB: columna agregada event.description")
            if "value1" not in col_names:
                db.session.execute(text("ALTER TABLE event ADD COLUMN value1 REAL"))
                logger.info("DB: columna agregada event.value1")
            if "value2" not in col_names:
                db.session.execute(text("ALTER TABLE event ADD COLUMN value2 REAL"))
                logger.info("DB: columna agregada event.value2")

        elif dialect == "postgresql":
            for table, column, col_type in [
                ("bus", "description", "TEXT"),
                ("event", "description", "TEXT"),
                ("event", "value1", "DOUBLE PRECISION"),
                ("event", "value2", "DOUBLE PRECISION"),
            ]:
                existing = {c["name"] for c in inspector.get_columns(table)}
                if column not in existing:
                    db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                    logger.info("DB: columna agregada %s.%s", table, column)

    except Exception as exc:
        logger.warning("DB: no se pudo validar/crear columnas opcionales: %s", exc)

    db.session.commit()


def initialize_database():
    """Verifica si existe al menos un administrador y deja el setup inicial listo."""
    admin_count = User.query.filter_by(role="admin").count()
    if admin_count == 0:
        logger.warning("No hay usuarios administradores. Se requiere configuracion inicial desde /setup.")
        return

    logger.info("Configuracion inicial verificada. Administradores activos: %s", admin_count)
