from app.extensions import db

class Bus(db.Model):
    """Modelo principal de vehículo (bus) con metadatos operativos."""
    __tablename__ = 'bus'
    id = db.Column(db.Integer, primary_key=True)
    plate = db.Column(db.String(20), nullable=False, unique=True)
    driver = db.Column(db.String(50))
    status = db.Column(db.String(20), default="Activo")
    # Relaciones (backrefs para consultas inversas)
    events = db.relationship('Event', backref='bus', lazy=True)
    locations = db.relationship('Location', backref='bus', lazy=True)
    maintenances = db.relationship('Maintenance', backref='bus', lazy=True)