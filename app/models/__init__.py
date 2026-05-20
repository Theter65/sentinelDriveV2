"""Paquete de modelos SQLAlchemy de la plataforma."""

# app/models/__init__.py
# Solo exporta las clases de modelos (no funciones de inicialización)
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
"""Paquete de modelos SQLAlchemy de la plataforma."""
