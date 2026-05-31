# app/routes/__init__.py - Paquete de blueprints HTTP
#
# Importación centralizada de todos los blueprints para registro
# en app/__init__.py mediante register_blueprint().
# Cada blueprint agrupa rutas por dominio funcional.
# =============================================================================

from .auth import auth_bp
from .dashboard import dashboard_bp
from .buses import buses_bp
from .tracking import tracking_bp
from .events import events_bp
from .reports import reports_bp
from .maintenance import maintenance_bp
from .users import users_bp
from .analytics import analytics_bp

# Lista explícita de blueprints para importación selectiva
__all__ = [
    "auth_bp",
    "dashboard_bp",
    "buses_bp",
    "tracking_bp",
    "events_bp",
    "reports_bp",
    "maintenance_bp",
    "users_bp",
    "analytics_bp",
]
