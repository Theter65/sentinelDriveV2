from datetime import timedelta

from flask import Blueprint, render_template
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.decorators import login_required
from app.extensions import db
from app.models.bus import Bus
from app.models.event import Event
from app.models.location import Location
from app.models.maintenance import Maintenance
from app.mqtt.subscriber import MQTT_STATE
from app.utils.logging import get_logger
from app.utils.time import ECUADOR_TZ, ecuador_now


logger = get_logger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    now = ecuador_now()
    one_minute_ago = now - timedelta(seconds=60)

    total_buses = Bus.query.count()
    active_buses = Bus.query.filter(Bus.status == "Activo").count()
    total_events = Event.query.count()
    pending_maintenances = Maintenance.query.filter(Maintenance.status == "Pendiente").count()

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
        if last_seen and getattr(last_seen, "tzinfo", None) is None:
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

    mqtt_connected = bool(MQTT_STATE.get("connected"))
    system_ok = mqtt_connected and connected_count > 0

    return render_template(
        "dashboard.html",
        now=now,
        mqtt_state=MQTT_STATE,
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
