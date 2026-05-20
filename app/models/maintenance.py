"""Modelo de mantenimientos asociados a cada bus de la flota."""

from app.extensions import db
from app.utils.time import ecuador_now


class Maintenance(db.Model):
    """Registro de mantenimientos preventivos/correctivos."""

    __tablename__ = "maintenance"
    __table_args__ = (
        db.Index("ix_maintenance_bus_date", "bus_id", "date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(db.Integer, db.ForeignKey("bus.id"), nullable=False, index=True)
    description = db.Column(db.String(200), nullable=False)
    date = db.Column(
        db.DateTime(timezone=True),
        default=ecuador_now,
        nullable=False,
        index=True,
    )
    status = db.Column(db.String(20), default="Pendiente")
