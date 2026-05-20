"""Modelo de eventos operativos recibidos desde MQTT o consultados en reportes."""

from app.extensions import db
from app.utils.time import ecuador_now


class Event(db.Model):
    """Registro de eventos criticos detectados."""

    __tablename__ = "event"
    __table_args__ = (
        db.Index("ix_event_bus_timestamp", "bus_id", "timestamp"),
    )

    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(
        db.Integer,
        db.ForeignKey("bus.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type = db.Column(db.String(50), nullable=False, index=True)
    value = db.Column(db.Float(precision=2), nullable=True)
    # Campo opcional para eventos extendidos (p. ej. tipo "Otros" con sensores extra)
    description = db.Column(db.String(300), nullable=True)
    latitude = db.Column(db.Float(precision=8), nullable=True)
    longitude = db.Column(db.Float(precision=8), nullable=True)
    timestamp = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=ecuador_now,
        index=True,
    )

    def __repr__(self):
        return f"<Event {self.type} en bus {self.bus_id} a {self.timestamp}>"
