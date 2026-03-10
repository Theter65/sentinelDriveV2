from flask import Blueprint, render_template, request, redirect, url_for

from app.decorators import require_admin
from app.extensions import db
from app.models.bus import Bus
from app.models.maintenance import Maintenance
from app.utils.logging import get_logger


logger = get_logger(__name__)

maintenance_bp = Blueprint("maintenance", __name__)


def _maintenance_page_context(error=None):
    return {
        "maintenances": Maintenance.query.order_by(Maintenance.date.desc()).all(),
        "buses": Bus.query.order_by(Bus.id.asc()).all(),
        "error": error,
    }


@maintenance_bp.route("/maintenance", methods=["GET", "POST"])
@require_admin
def maintenance():
    """Pagina principal de gestion de mantenimientos."""
    if request.method == "POST":
        bus_id = request.form.get("bus_id")
        description = (request.form.get("description") or "").strip()

        if not bus_id or not description:
            return render_template("maintenance.html", **_maintenance_page_context("Todos los campos son obligatorios"))

        try:
            bus_id = int(bus_id)
        except ValueError:
            return render_template("maintenance.html", **_maintenance_page_context("ID de bus invalido"))

        if not db.session.get(Bus, bus_id):
            return render_template("maintenance.html", **_maintenance_page_context("El bus seleccionado no existe"))

        new_maintenance = Maintenance(bus_id=bus_id, description=description)
        db.session.add(new_maintenance)
        db.session.commit()

        logger.info("Nuevo mantenimiento registrado: bus %s", bus_id)
        return redirect(url_for("maintenance.maintenance"))

    return render_template("maintenance.html", **_maintenance_page_context())


@maintenance_bp.route("/maintenance/toggle/<int:m_id>", methods=["POST"])
@require_admin
def toggle_maintenance(m_id):
    """Cambia el estado de un mantenimiento: Pendiente <-> Completado."""
    maintenance_record = Maintenance.query.get_or_404(m_id)
    maintenance_record.status = (
        "Completado" if maintenance_record.status == "Pendiente" else "Pendiente"
    )
    db.session.commit()
    logger.info("Estado cambiado para mantenimiento %s: %s", m_id, maintenance_record.status)
    return redirect(url_for("maintenance.maintenance"))


@maintenance_bp.route("/maintenance/delete/<int:m_id>", methods=["POST"])
@require_admin
def delete_maintenance(m_id):
    """Elimina un registro de mantenimiento."""
    maintenance_record = Maintenance.query.get_or_404(m_id)
    bus_plate = maintenance_record.bus.plate
    db.session.delete(maintenance_record)
    db.session.commit()
    logger.info("Mantenimiento %s eliminado (bus: %s)", m_id, bus_plate)
    return redirect(url_for("maintenance.maintenance"))
