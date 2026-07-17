# app/models/location.py - Modelo de posiciones GPS
#
# Almacena el historial de ubicaciones GPS por bus: latitud,
# longitud, velocidad y timestamp. Índice compuesto por bus+fecha.
# =============================================================================

from app.extensions import db
from app.utils.time import ecuador_now


class Location(db.Model):
    """Registro de posiciones GPS."""

    __tablename__ = "location"
    __table_args__ = (
        db.Index("ix_location_bus_timestamp", "bus_id", "timestamp"),
    )

    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(db.Integer, db.ForeignKey("bus.id"), nullable=False, index=True)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    speed = db.Column(db.Float)
    timestamp = db.Column(
        db.DateTime(timezone=False),
        default=ecuador_now,
        nullable=False,
        index=True,
    )
