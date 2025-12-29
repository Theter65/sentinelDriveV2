from flask import Blueprint, render_template, jsonify
from app.decorators import login_required
from app.extensions import db
from app.models.bus import Bus
from app.models.location import Location
from app.utils.logging import get_logger

logger = get_logger(__name__)

tracking_bp = Blueprint('tracking', __name__)

@tracking_bp.route("/tracking")
@login_required
def tracking():
    """Seguimiento GPS con selector de bus y mapa interactivo."""
    buses = Bus.query.all()
    logger.debug(f"Mostrando {len(buses)} buses en el mapa de seguimiento")
    return render_template("tracking.html", buses=buses)

@tracking_bp.route("/api/last-position/<int:bus_id>")
@login_required
def api_last_position(bus_id):
    """API JSON para obtener la última posición de un bus específico."""
    location = (
        Location.query
        .filter_by(bus_id=bus_id)
        .order_by(Location.timestamp.desc())
        .first()
    )
    
    if not location:
        logger.warning(f"No hay datos GPS para bus_id={bus_id}")
        return jsonify({"error": "No hay datos GPS para este bus"}), 404
    
    bus = Bus.query.get(bus_id)
    if not bus:
        logger.error(f"Bus con ID {bus_id} no encontrado en la API de posición")
        return jsonify({"error": "Bus no encontrado"}), 404
    
    response = {
        "bus": {
            "id": bus.id,
            "plate": bus.plate,
            "driver": bus.driver
        },
        "lat": location.lat,
        "lon": location.lon,
        "speed": location.speed,
        "timestamp": location.timestamp.isoformat()
    }
    
    logger.debug(f"Última posición devuelta para bus {bus_id}: {response['lat']}, {response['lon']}")
    return jsonify(response)