"""Fabrica principal de la aplicacion Flask y registro de modulos."""

# =============================================================================
# app/__init__.py - Fábrica de aplicación Flask (Application Factory)
#
# Crea y configura la aplicación sin ejecutar consultas a BD.
# La inicialización de datos se mueve a run.py para evitar problemas de contexto.
# =============================================================================

from flask import Flask
from pathlib import Path
from werkzeug.middleware.proxy_fix import ProxyFix
from .config import Config
from .extensions import db, csrf
from .models.init_data import ensure_database_indexes
from .models.system_setting import SystemSetting  # noqa: F401
from .models.analytics import AnalyticsRun  # noqa: F401
from .utils.logging import get_logger
from .utils.time import ecuador_now
from .utils.system_settings import get_persisted_mqtt_state

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
from .routes.analytics import analytics_bp


logger = get_logger(__name__)

def create_app(config_class=Config):
    """
    Fábrica de aplicación Flask.
    - Crea y configura la app.
    - Inicializa extensiones y registra blueprints.
    - Solo crea tablas (db.create_all), sin datos iniciales aquí.
    """
    # static/ lives at repo root (../static). Without this, Flask looks for app/static.
    base_dir = Path(__file__).resolve().parent.parent
    instance_dir = base_dir / "instance"
    instance_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Instance folder verificado/creado: %s", instance_dir)

    app = Flask(
        __name__,
        static_folder=str(base_dir / "static"),
        instance_path=str(instance_dir),
    )
    app.config.from_object(config_class)

    if app.config.get("USE_PROXY_FIX"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
        logger.info("ProxyFix activado para cabeceras X-Forwarded-*")

    @app.context_processor
    def _inject_static_version():
        """Evita cache agresivo del navegador para assets locales (CSS/JS) en desarrollo."""
        v = 0
        for p in (
            base_dir / "static" / "css" / "style.css",
            base_dir / "static" / "css" / "theme.css",
            base_dir / "static" / "css" / "glass.css",
            base_dir / "static" / "js" / "app.js",
            base_dir / "static" / "js" / "chart-theme.js",
            base_dir / "static" / "js" / "theme-switcher.js",
        ):
            try:
                v = max(v, int(p.stat().st_mtime))
            except OSError:
                pass
        mqtt_state = get_persisted_mqtt_state(app.config)

        return {
            "static_version": v,
            "layout_mqtt_state": mqtt_state,
            "layout_mqtt_ready": bool(mqtt_state.get("configuration_ready")),
            "layout_mqtt_connected": bool(mqtt_state.get("connected")),
            "layout_mqtt_label": mqtt_state.get("label", "MQTT no configurado"),
            "current_year": ecuador_now().year,
        }

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
    app.register_blueprint(analytics_bp)

    # Crear tablas (sin datos iniciales)
    with app.app_context():
        db.create_all()
        ensure_database_indexes()
        logger.info("Base de datos inicializada/verificada")

    return app
