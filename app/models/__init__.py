# app/models/__init__.py - Paquete de modelos SQLAlchemy
#
# Centraliza la importación de todas las clases modelo para facilitar
# el acceso desde otros módulos (ej: from app.models import Bus).
# No incluye funciones de inicialización de datos (init_data.py).
# =============================================================================

from .user import User
from .bus import Bus
from .event import Event
from .location import Location
from .maintenance import Maintenance
from .system_setting import SystemSetting
from .analytics import (
    AnalyticsRun,
    EventMagnitudeStatistic,
    EventTypeStatistic,
    HourlyEventStatistic,
    SpeedHistogramBin,
    VehicleStatisticsSummary,
)
