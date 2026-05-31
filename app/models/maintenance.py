# app/models/maintenance.py - Modelo de mantenimientos por bus
#
# Almacena registros de mantenimiento preventivo y correctivo para
# cada vehículo de la flota. Cada mantenimiento tiene un estado
# que permite seguimiento (Pendiente / Completado).
# =============================================================================

from app.extensions import db
from app.utils.time import ecuador_now


class Maintenance(db.Model):
    """Registro de mantenimientos preventivos/correctivos por bus."""

    __tablename__ = "maintenance"

    # Índice compuesto para consultas por bus + fecha
    __table_args__ = (
        db.Index("ix_maintenance_bus_date", "bus_id", "date"),
    )

    # Identificador único del registro
    id = db.Column(db.Integer, primary_key=True)

    # Relación con el bus (clave foránea)
    bus_id = db.Column(db.Integer, db.ForeignKey("bus.id"), nullable=False, index=True)

    # Descripción de la tarea de mantenimiento realizada o pendiente
    description = db.Column(db.String(200), nullable=False)

    # Fecha del mantenimiento (por defecto: momento de creación)
    date = db.Column(
        db.DateTime(timezone=True),
        default=ecuador_now,
        nullable=False,
        index=True,
    )

    # Estado: Pendiente | Completado
    status = db.Column(db.String(20), default="Pendiente")
