# =============================================================================
# app/routes/maintenance.py - Blueprint de gestión de mantenimientos
#
# Funcionalidades:
# - Mostrar lista de mantenimientos
# - Registrar nuevo mantenimiento (POST)
# - Cambiar estado (toggle)
# - Eliminar mantenimiento
# =============================================================================

from flask import Blueprint, render_template, request, redirect, url_for
from app.decorators import login_required, require_admin
from app.extensions import db
from app.models.maintenance import Maintenance
from app.models.bus import Bus
from app.utils.logging import get_logger

logger = get_logger(__name__)

maintenance_bp = Blueprint('maintenance', __name__)

@maintenance_bp.route("/maintenance", methods=["GET", "POST"])
@require_admin
def maintenance():
    """
    Página principal de gestión de mantenimientos.
    - GET: Muestra lista y formulario
    - POST: Registra un nuevo mantenimiento
    """
    if request.method == "POST":
        bus_id = request.form.get("bus_id")
        description = request.form.get("description")

        # Validaciones básicas de seguridad
        if not bus_id or not description:
            return render_template("maintenance.html",
                                   maintenances=Maintenance.query.order_by(Maintenance.date.desc()).all(),
                                   buses=Bus.query.all(),
                                   error="Todos los campos son obligatorios")

        if not description.strip():
            return render_template("maintenance.html",
                                   maintenances=Maintenance.query.order_by(Maintenance.date.desc()).all(),
                                   buses=Bus.query.all(),
                                   error="La descripción no puede estar vacía")

        try:
            bus_id = int(bus_id)
            if not Bus.query.get(bus_id):
                return render_template("maintenance.html",
                                       maintenances=Maintenance.query.order_by(Maintenance.date.desc()).all(),
                                       buses=Bus.query.all(),
                                       error="El bus seleccionado no existe")
        except ValueError:
            return render_template("maintenance.html",
                                   maintenances=Maintenance.query.order_by(Maintenance.date.desc()).all(),
                                   buses=Bus.query.all(),
                                   error="ID de bus inválido")

        # Crear nuevo mantenimiento
        new_maintenance = Maintenance(
            bus_id=bus_id,
            description=description.strip()
        )
        db.session.add(new_maintenance)
        db.session.commit()

        logger.info(f"Nuevo mantenimiento registrado: bus {bus_id}, descripción: {description}")
        return redirect(url_for("maintenance.maintenance"))

    # GET: mostrar página normal
    maintenances = Maintenance.query.order_by(Maintenance.date.desc()).all()
    buses = Bus.query.all()
    return render_template("maintenance.html", maintenances=maintenances, buses=buses)

@maintenance_bp.route("/maintenance/toggle/<int:m_id>", methods=["POST"])
@require_admin
def toggle_maintenance(m_id):
    """Cambia el estado de un mantenimiento: Pendiente ↔ Completado."""
    maintenance = Maintenance.query.get_or_404(m_id)
    maintenance.status = "Completado" if maintenance.status == "Pendiente" else "Pendiente"
    db.session.commit()
    logger.info(f"Estado cambiado para mantenimiento {m_id}: {maintenance.status}")
    return redirect(url_for("maintenance.maintenance"))

@maintenance_bp.route("/maintenance/delete/<int:m_id>", methods=["POST"])
@require_admin
def delete_maintenance(m_id):
    """Elimina un registro de mantenimiento."""
    maintenance = Maintenance.query.get_or_404(m_id)
    bus_plate = maintenance.bus.plate
    db.session.delete(maintenance)
    db.session.commit()
    logger.info(f"Mantenimiento {m_id} eliminado (bus: {bus_plate})")
    return redirect(url_for("maintenance.maintenance"))