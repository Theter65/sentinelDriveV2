# app/routes/maintenance.py - Gestión de mantenimientos
#
# CRUD de mantenimientos preventivos y correctivos por bus.
# Incluye toggle de estado (Pendiente <-> Completado) y
# eliminación de registros. Solo accesible para admin.
# =============================================================================

import math
from flask import Blueprint, render_template, request, redirect, url_for

from app.decorators import require_admin
from app.extensions import db
from app.models.bus import Bus
from app.models.maintenance import Maintenance
from app.utils.logging import get_logger


logger = get_logger(__name__)

maintenance_bp = Blueprint("maintenance", __name__)

MAINTENANCE_PAGE_SIZE = 20


def _maintenance_page_context(error=None, page=1):
    total = Maintenance.query.count()
    total_pages = max(1, math.ceil(total / MAINTENANCE_PAGE_SIZE))
    page = max(1, min(page, total_pages))
    maintenances = (
        Maintenance.query
        .order_by(Maintenance.date.desc())
        .offset((page - 1) * MAINTENANCE_PAGE_SIZE)
        .limit(MAINTENANCE_PAGE_SIZE)
        .all()
    )
    return {
        "maintenances": maintenances,
        "buses": Bus.query.order_by(Bus.id.asc()).all(),
        "error": error,
        "page": page,
        "total_pages": total_pages,
        "total_records": total,
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
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Error al crear mantenimiento para bus %s", bus_id)
            return render_template("maintenance.html", **_maintenance_page_context("Error al guardar el mantenimiento"))

        logger.info("Nuevo mantenimiento registrado: bus %s", bus_id)
        return redirect(url_for("maintenance.maintenance"))

    page = request.args.get("page", 1, type=int)
    return render_template("maintenance.html", **_maintenance_page_context(page=page))


@maintenance_bp.route("/maintenance/toggle/<int:m_id>", methods=["POST"])
@require_admin
def toggle_maintenance(m_id):
    """Cambia el estado de un mantenimiento: Pendiente <-> Completado."""
    maintenance_record = Maintenance.query.get_or_404(m_id)
    maintenance_record.status = (
        "Completado" if maintenance_record.status == "Pendiente" else "Pendiente"
    )
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Error al cambiar estado del mantenimiento %s", m_id)
        flash("Error al cambiar el estado.", "danger")
    page = request.args.get("page", 1, type=int)
    logger.info("Estado cambiado para mantenimiento %s: %s", m_id, maintenance_record.status)
    return redirect(url_for("maintenance.maintenance", page=page))


@maintenance_bp.route("/maintenance/delete/<int:m_id>", methods=["POST"])
@require_admin
def delete_maintenance(m_id):
    """Elimina un registro de mantenimiento."""
    maintenance_record = Maintenance.query.get_or_404(m_id)
    bus_plate = maintenance_record.bus.plate
    db.session.delete(maintenance_record)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Error al eliminar mantenimiento %s", m_id)
        flash("Error al eliminar el mantenimiento.", "danger")
    page = request.args.get("page", 1, type=int)
    logger.info("Mantenimiento %s eliminado (bus: %s)", m_id, bus_plate)
    return redirect(url_for("maintenance.maintenance", page=page))
