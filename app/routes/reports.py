# =============================================================================
# app/routes/reports.py - Blueprint de reportes estadísticos
#
# Genera métricas por bus y estadísticas agregadas:
# - Total de eventos
# - Eventos peligrosos
# - Distribución de tipos de eventos
# - Velocidad promedio por día
# =============================================================================

from flask import Blueprint, render_template
from sqlalchemy import func
from app.decorators import login_required
from app.extensions import db
from app.models.bus import Bus
from app.models.event import Event
from app.models.location import Location
from app.utils.logging import get_logger

logger = get_logger(__name__)

reports_bp = Blueprint("reports", __name__)

EVENT_TYPES = [
    "Exceso de velocidad",
    "Frenado brusco",
    "Curva pronunciada"
]


@reports_bp.route("/reports")
@login_required
def reports():
    buses = Bus.query.all()
    logger.info(f"Generando reportes para {len(buses)} buses")

    # ==========================================================
    # TABLA PRINCIPAL (ya la usabas)
    # ==========================================================
    report_data = []
    for bus in buses:
        total_events = Event.query.filter_by(bus_id=bus.id).count()

        dangerous_events = Event.query.filter(
            Event.bus_id == bus.id,
            Event.type.in_(EVENT_TYPES)
        ).count()

        report_data.append({
            "bus": bus,
            "dangerous": dangerous_events
        })

    # ==========================================================
    # GRÁFICA 1: Eventos peligrosos por bus
    # ==========================================================
    bus_labels = []
    dangerous_counts = []

    for bus in buses:
        bus_labels.append(bus.plate)

        count = Event.query.filter(
            Event.bus_id == bus.id,
            Event.type.in_(EVENT_TYPES)
        ).count()

        dangerous_counts.append(count)

    # ==========================================================
    # GRÁFICA 2: Distribución de tipos de eventos
    # ==========================================================
    event_types = EVENT_TYPES.copy()
    event_type_counts = []

    for event_type in event_types:
        count = Event.query.filter_by(type=event_type).count()
        event_type_counts.append(count)

    # ==========================================================
    # GRÁFICA 3: Velocidad promedio por día
    # (solo si hay datos de ubicación)
    # ==========================================================
    speed_by_day = (
        db.session.query(
            func.date(Location.timestamp).label("day"),
            func.avg(Location.speed).label("avg_speed")
        )
        .filter(Location.speed.isnot(None))
        .group_by(func.date(Location.timestamp))
        .order_by(func.date(Location.timestamp))
        .all()
    )

    speed_dates = []
    avg_speeds = []

    for row in speed_by_day:
        speed_dates.append(str(row.day))
        avg_speeds.append(round(row.avg_speed, 2) if row.avg_speed else 0)

    logger.debug("Reportes generados correctamente")

    # ==========================================================
    # RENDER
    # ==========================================================
    return render_template(
        "reports.html",
        report_data=report_data,
        bus_labels=bus_labels,
        dangerous_counts=dangerous_counts,
        event_types=event_types,
        event_type_counts=event_type_counts,
        speed_dates=speed_dates,
        avg_speeds=avg_speeds
    )
