from flask import Blueprint, jsonify, render_template

from app.decorators import login_required
from app.extensions import db
from app.models.bus import Bus
from app.models.location import Location
from app.utils.logging import get_logger


logger = get_logger(__name__)

tracking_bp = Blueprint("tracking", __name__)


@tracking_bp.route("/tracking")
@login_required
def tracking():
    """Seguimiento GPS con selector de bus y mapa interactivo."""
    buses = Bus.query.order_by(Bus.plate.asc()).all()
    logger.debug("Mostrando %s buses en el mapa de seguimiento", len(buses))
    return render_template("tracking.html", buses=buses)


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
