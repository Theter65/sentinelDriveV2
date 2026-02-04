# app/models/event.py
from app.extensions import db
from datetime import datetime
from zoneinfo import ZoneInfo

class Event(db.Model):
    """
    Registro de eventos críticos detectados (seguridad vial).
    Incluye posición geoespacial exacta del evento para análisis y trazabilidad.
    """
    __tablename__ = 'event'

    id = db.Column(db.Integer, primary_key=True)
    
    bus_id = db.Column(
        db.Integer,
        db.ForeignKey('bus.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    type = db.Column(db.String(50), nullable=False, index=True)
    
    value = db.Column(db.Float(precision=2), nullable=True)
    
    # Posición exacta donde ocurrió el evento (lat/lon)
    latitude = db.Column(db.Float(precision=8), nullable=True)
    longitude = db.Column(db.Float(precision=8), nullable=True)
    
    # Timestamp preciso en zona Ecuador (America/Guayaquil, UTC-5)
    timestamp = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(ZoneInfo("America/Guayaquil")),
        index=True
    )

    # Relación bidireccional (inferida del backref en Bus)
    # No definimos aquí nada extra → SQLAlchemy lo maneja automáticamente

    def __repr__(self):
        return f"<Event {self.type} en bus {self.bus_id} a {self.timestamp}>"