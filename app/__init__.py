# =============================================================================
# app/__init__.py - Fábrica de aplicación Flask (Application Factory)
#
# Crea y configura la aplicación sin ejecutar consultas a BD.
# La inicialización de datos se mueve a run.py para evitar problemas de contexto.
# =============================================================================

from flask import Flask
from .config import Config
from .extensions import db, csrf

# Importación de blueprints (rutas modulares)
from .routes.auth import auth_bp
from .routes.dashboard import dashboard_bp
from .routes.buses import buses_bp
from .routes.tracking import tracking_bp
from .routes.events import events_bp
from .routes.reports import reports_bp
from .routes.maintenance import maintenance_bp
from .routes.users import users_bp

def create_app(config_class=Config):
    """
    Fábrica de aplicación Flask.
    - Crea y configura la app.
    - Inicializa extensiones y registra blueprints.
    - Solo crea tablas (db.create_all), sin datos iniciales aquí.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

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

    # Crear tablas (sin datos iniciales)
    with app.app_context():
        db.create_all()

    return app