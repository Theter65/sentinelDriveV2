# app/routes/dashboard.py - Panel principal y resumen operativo
#
# Renderiza el dashboard con KPIs: estado del sistema, conteo de buses,
# eventos recientes, mantenimientos pendientes y salud de conexión
# de cada vehículo (último GPS recibido en los últimos 60 segundos).
# =============================================================================

from datetime import timedelta

from flask import Blueprint, current_app, render_template
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.decorators import login_required
from app.extensions import db
from app.models.bus import Bus
from app.models.event import Event
from app.models.location import Location
from app.models.maintenance import Maintenance
from app.utils.logging import get_logger
from app.utils.system_settings import get_cached_persisted_mqtt_state
from app.utils.time import ECUADOR_TZ, ecuador_now


logger = get_logger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    """Compone metricas generales y estado de buses para el panel."""
    now = ecuador_now()
    one_minute_ago = now - timedelta(seconds=60)

    metrics = db.session.execute(
        select(
            select(func.count(Bus.id)).scalar_subquery(),
            select(func.count(Bus.id)).where(Bus.status == "Activo").scalar_subquery(),
            select(func.count(Event.id)).scalar_subquery(),
            select(func.count(Maintenance.id)).where(Maintenance.status == "Pendiente").scalar_subquery(),
        )
    ).one()
    total_buses, active_buses, total_events, pending_maintenances = metrics

    last_seen_sq = (
        db.session.query(
            Location.bus_id.label("bus_id"),
            func.max(Location.timestamp).label("last_seen"),
        )
        .group_by(Location.bus_id)
        .subquery()
    )

    bus_rows = (
        db.session.query(Bus, last_seen_sq.c.last_seen)
        .outerjoin(last_seen_sq, Bus.id == last_seen_sq.c.bus_id)
        .order_by(Bus.id.asc())
        .all()
    )

    bus_health = []
    connected_count = 0
    for bus, last_seen in bus_rows:
        if last_seen:
            if getattr(last_seen, "tzinfo", None) is not None:
                last_seen = last_seen.replace(tzinfo=None)
            last_seen = last_seen.replace(tzinfo=ECUADOR_TZ)
        is_connected = bool(last_seen and last_seen >= one_minute_ago)
        if is_connected:
            connected_count += 1
        seconds_since = int((now - last_seen).total_seconds()) if last_seen else None
        bus_health.append(
            {
                "id": bus.id,
                "plate": bus.plate,
                "driver": bus.driver,
                "status": bus.status,
                "description": getattr(bus, "description", None),
                "last_seen": last_seen,
                "seconds_since": seconds_since,
                "connected": is_connected,
            }
        )

    disconnected_count = max(0, total_buses - connected_count)

    last_events = (
        Event.query.options(joinedload(Event.bus))
        .order_by(Event.timestamp.desc())
        .limit(5)
        .all()
    )

    mqtt_state = get_cached_persisted_mqtt_state(current_app.config)
    mqtt_connected = bool(mqtt_state.get("connected"))
    system_ok = mqtt_connected and connected_count > 0

    return render_template(
        "dashboard.html",
        now=now,
        mqtt_state=mqtt_state,
        mqtt_connected=mqtt_connected,
        system_ok=system_ok,
        total_buses=total_buses,
        active_buses=active_buses,
        connected_buses=connected_count,
        disconnected_buses=disconnected_count,
        total_events=total_events,
        pending_maintenances=pending_maintenances,
        last_events=last_events,
        bus_health=bus_health,
    )
