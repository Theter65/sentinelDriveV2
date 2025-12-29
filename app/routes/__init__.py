# app/routes/__init__.py
# Importación de todos los blueprints para registro centralizado en app/__init__.py
# Esto facilita la escalabilidad y mantenimiento del sistema

from .auth import auth_bp
from .dashboard import dashboard_bp
from .buses import buses_bp
from .tracking import tracking_bp
from .events import events_bp
from .reports import reports_bp
from .maintenance import maintenance_bp
from .users import users_bp

__all__ = [
    "auth_bp",
    "dashboard_bp",
    "buses_bp",
    "tracking_bp",
    "events_bp",
    "reports_bp",
    "maintenance_bp",
    "users_bp"
]