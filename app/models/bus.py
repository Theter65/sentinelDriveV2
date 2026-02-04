# app/models/bus.py
from app.extensions import db

class Bus(db.Model):
    __tablename__ = 'bus'
    id = db.Column(db.Integer, primary_key=True)
    plate = db.Column(db.String(20), nullable=False, unique=True)
    driver = db.Column(db.String(50))
    status = db.Column(db.String(20), default="Activo")

    # Relación principal con backref → crea 'bus' automáticamente en Event
    events = db.relationship(
        'Event',
        backref='bus',  # ← Solo aquí se define el backref
        lazy=True,
        cascade='all, delete-orphan'
    )

    locations = db.relationship(
        'Location',
        backref='bus',
        lazy=True,
        cascade='all, delete-orphan'
    )

    maintenances = db.relationship(
        'Maintenance',
        backref='bus',
        lazy=True,
        cascade='all, delete-orphan'
    )