"""Rutas de seguimiento GPS y API de ultima posicion."""

from flask import Blueprint, jsonify, render_template, request

from app.decorators import login_required
from app.extensions import db
from app.models.bus import Bus
from app.models.event import Event
from app.models.location import Location
from app.utils.logging import get_logger


logger = get_logger(__name__)

tracking_bp = Blueprint("tracking", __name__)


@tracking_bp.route("/tracking")
@login_required
def tracking():
    """Seguimiento GPS con selector de bus y mapa interactivo."""
    buses = Bus.query.order_by(Bus.plate.asc()).all()
    selected_event = _selected_event_from_request()
    logger.debug("Mostrando %s buses en el mapa de seguimiento", len(buses))
    return render_template("tracking.html", buses=buses, selected_event=selected_event)


def _selected_event_from_request():
    """Construye un marcador temporal para centrar el mapa sin alterar el seguimiento normal."""
    event_id = request.args.get("event_id", type=int)
    event = db.session.get(Event, event_id) if event_id else None
    lat = event.latitude if event else request.args.get("lat", type=float)
    lon = event.longitude if event else request.args.get("lon", type=float)
    if lat is None or lon is None:
        return None

    bus = event.bus if event and event.bus else (db.session.get(Bus, event.bus_id) if event and event.bus_id else None)
    return {
        "id": event.id if event else event_id,
        "bus_id": event.bus_id if event else request.args.get("bus_id", type=int),
        "bus_label": bus.plate if bus else (f"Bus {event.bus_id}" if event and event.bus_id else "Sin bus"),
        "type": event.type if event else "Evento seleccionado",
        "value": event.value if event and event.value is not None else None,
        "description": getattr(event, "description", None) if event else None,
        "timestamp": event.timestamp.isoformat() if event and event.timestamp else None,
        "lat": lat,
        "lon": lon,
    }


@tracking_bp.route("/api/last-position/<int:bus_id>")
@login_required
def api_last_position(bus_id):
    """API JSON para obtener la ultima posicion de un bus especifico."""
    bus = db.session.get(Bus, bus_id)
    if not bus:
        logger.error("Bus con ID %s no encontrado en la API de posicion", bus_id)
        return jsonify({"error": "Bus no encontrado"}), 404

    location = (
        Location.query.filter_by(bus_id=bus_id)
        .order_by(Location.timestamp.desc())
        .first()
    )
    if not location:
        logger.warning("No hay datos GPS para bus_id=%s", bus_id)
        return jsonify({"error": "No hay datos GPS para este bus"}), 404

    response = {
        "bus": {
            "id": bus.id,
            "plate": bus.plate,
            "driver": bus.driver,
            "status": bus.status,
            "description": getattr(bus, "description", None),
        },
        "lat": location.lat,
        "lon": location.lon,
        "speed": location.speed or 0,
        "timestamp": location.timestamp.isoformat(),
    }

    logger.debug("Ultima posicion devuelta para bus %s: %s, %s", bus_id, response["lat"], response["lon"])
    return jsonify(response)
