"""Modelo de buses y relaciones con eventos, ubicaciones y mantenimientos."""

from app.extensions import db

class Bus(db.Model):
    """Vehiculo registrado dentro de la flota monitoreada."""

    __tablename__ = 'bus'
    id = db.Column(db.Integer, primary_key=True)
    plate = db.Column(db.String(20), nullable=False, unique=True)
    driver = db.Column(db.String(50))
    status = db.Column(db.String(20), default="Activo")
    description = db.Column(db.String(300), nullable=True)

    # Relacion principal: expone event.bus y elimina eventos al borrar el bus.
    events = db.relationship(
        'Event',
        backref='bus',
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
