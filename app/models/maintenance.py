from app.extensions import db
from datetime import datetime

class Maintenance(db.Model):
    """Registro de mantenimientos preventivos/correctivos."""
    __tablename__ = 'maintenance'
    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(db.Integer, db.ForeignKey('bus.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(20), default="Pendiente")