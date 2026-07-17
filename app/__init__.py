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
from .utils.time import ECUADOR_TZ, ecuador_now
from .utils.system_settings import get_persisted_mqtt_state
import time
import threading

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

# Cache para MQTT state en context processor (evita DB query en cada request)
_mqtt_state_cache = {"data": None, "ts": 0.0}
_mqtt_state_lock = threading.Lock()
_MQTT_STATE_CACHE_TTL = 5.0  # segundos

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

        # Usar cache thread-safe para evitar DB query en cada request
        now = time.time()
        with _mqtt_state_lock:
            if _mqtt_state_cache["data"] is None or (now - _mqtt_state_cache["ts"]) > _MQTT_STATE_CACHE_TTL:
                _mqtt_state_cache["data"] = get_persisted_mqtt_state(app.config)
                _mqtt_state_cache["ts"] = now
            mqtt_state = _mqtt_state_cache["data"]

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

    @app.template_filter("ecuador_time")
    def _ecuador_time_filter(dt, fmt="%Y-%m-%d %H:%M:%S"):
        if dt is None:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ECUADOR_TZ)
        return dt.astimezone(ECUADOR_TZ).strftime(fmt)

    # Habilitar WAL mode para SQLite (permite lecturas concurrentes con 1 escritor)
    with app.app_context():
        if "sqlite" in app.config["SQLALCHEMY_DATABASE_URI"]:
            db.session.execute(db.text("PRAGMA journal_mode=WAL"))
            db.session.execute(db.text("PRAGMA busy_timeout=15000"))
            db.session.commit()
            logger.info("SQLite: WAL mode y busy_timeout=15s habilitados")

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
