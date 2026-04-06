# =============================================================================
# app/__init__.py - Fábrica de aplicación Flask (Application Factory)
#
# Crea y configura la aplicación sin ejecutar consultas a BD.
# La inicialización de datos se mueve a run.py para evitar problemas de contexto.
# =============================================================================

from flask import Flask
from pathlib import Path
from .config import Config
from .extensions import db, csrf
from .models.init_data import ensure_database_indexes

# Importación de blueprints (rutas modulares)
from .routes.auth import auth_bp
from .routes.dashboard import dashboard_bp
from .routes.buses import buses_bp
from .routes.tracking import tracking_bp
from .routes.events import events_bp
from .routes.reports import reports_bp
from .routes.maintenance import maintenance_bp
from .routes.users import users_bp
from .routes.admin import admin_bp

def create_app(config_class=Config):
    """
    Fábrica de aplicación Flask.
    - Crea y configura la app.
    - Inicializa extensiones y registra blueprints.
    - Solo crea tablas (db.create_all), sin datos iniciales aquí.
    """
    # static/ lives at repo root (../static). Without this, Flask looks for app/static.
    base_dir = Path(__file__).resolve().parent.parent
    app = Flask(__name__, static_folder=str(base_dir / "static"))
    app.config.from_object(config_class)

    @app.context_processor
    def _inject_static_version():
        """Evita cache agresivo del navegador para assets locales (CSS/JS) en desarrollo."""
        v = 0
        for p in (
            base_dir / "static" / "css" / "style.css",
            base_dir / "static" / "js" / "app.js",
        ):
            try:
                v = max(v, int(p.stat().st_mtime))
            except OSError:
                pass
        return {"static_version": v}

    # Inicializar extensiones globales
    db.init_app(app)
    csrf.init_app(app)

    # Registrar blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(buses_bp)
    app.register_blueprint(tracking_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(admin_bp)

    # Crear tablas (sin datos iniciales)
    with app.app_context():
        db.create_all()
        ensure_database_indexes()

    return app
