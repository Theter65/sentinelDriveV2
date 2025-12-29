from app.extensions import db
from datetime import datetime

class Event(db.Model):
    """Registro de eventos críticos detectados (seguridad vial)."""
    __tablename__ = 'event'
    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(db.Integer, db.ForeignKey('bus.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    value = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)