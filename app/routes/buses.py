# app/routes/buses.py - CRUD de buses de la flota
#
# Permite listar, crear, editar y eliminar buses registrados.
# Solo usuarios admin pueden modificar/eliminar; usuarios con rol
# básico pueden consultar la lista. Incluye exportación CSV.
# =============================================================================

from flask import Blueprint, render_template, request, redirect, url_for

from app.decorators import login_required, require_admin
from app.extensions import db
from app.models.bus import Bus
from app.utils.csv_export import csv_response
from app.utils.logging import get_logger


logger = get_logger(__name__)

buses_bp = Blueprint("buses", __name__)


def _normalize_bus_form():
    description = (request.form.get("description") or "").strip()
    return {
        "plate": (request.form.get("plate") or "").strip().upper(),
        "driver": (request.form.get("driver") or "").strip(),
        "status": (request.form.get("status") or "Activo").strip(),
        "description": description or None,
    }


@buses_bp.route("/buses")
@login_required
def buses():
    """Lista de todos los buses registrados."""
    buses_list = Bus.query.order_by(Bus.id.asc()).all()
    return render_template("buses.html", buses=buses_list)


@buses_bp.route("/add_bus", methods=["GET", "POST"])
@require_admin
def add_bus():
    """Formulario para registrar un nuevo bus."""
    if request.method == "POST":
        bus_id = request.form.get("id")
        form_data = _normalize_bus_form()
        try:
            bus_id = int(bus_id)
        except (TypeError, ValueError):
            return render_template("add_bus.html", error="ID invalido (debe ser numero)")

        if not form_data["plate"] or not form_data["driver"]:
            return render_template("add_bus.html", error="Placa y conductor son obligatorios")
        if db.session.get(Bus, bus_id):
            return render_template("add_bus.html", error="El ID ya existe")
        if Bus.query.filter_by(plate=form_data["plate"]).first():
            return render_template("add_bus.html", error="La placa ya existe")

        new_bus = Bus(id=bus_id, **form_data)
        db.session.add(new_bus)
        db.session.commit()
        logger.info("Bus registrado: ID %s, placa %s", bus_id, form_data["plate"])
        return redirect(url_for("buses.buses"))
    return render_template("add_bus.html")


@buses_bp.route("/bus/edit/<int:bus_id>", methods=["GET", "POST"])
@require_admin
def edit_bus(bus_id):
    """Editar placa, conductor y estado de un bus existente."""
    bus = Bus.query.get_or_404(bus_id)
    if request.method == "POST":
        form_data = _normalize_bus_form()
        if not form_data["plate"] or not form_data["driver"]:
            return render_template("edit_bus.html", bus=bus, error="Placa y conductor son obligatorios")

        duplicated_plate = (
            Bus.query.filter(Bus.plate == form_data["plate"], Bus.id != bus_id).first()
        )
        if duplicated_plate:
            return render_template("edit_bus.html", bus=bus, error="La placa ya esta asignada a otro bus")

        bus.plate = form_data["plate"]
        bus.driver = form_data["driver"]
        bus.status = form_data["status"]
        bus.description = form_data["description"]
        db.session.commit()
        logger.info("Bus editado: ID %s, placa %s, conductor %s", bus_id, bus.plate, bus.driver)
        return redirect(url_for("buses.buses"))
    return render_template("edit_bus.html", bus=bus)


@buses_bp.route("/bus/delete/<int:bus_id>", methods=["POST"])
@require_admin
def delete_bus(bus_id):
    """Eliminar un bus y toda su informacion asociada."""
    bus = Bus.query.get_or_404(bus_id)
    plate = bus.plate
    db.session.delete(bus)
    db.session.commit()
    logger.info("Bus eliminado completamente: ID %s, placa %s", bus_id, plate)
    return redirect(url_for("buses.buses"))


@buses_bp.route("/buses/export_csv")
@require_admin
def export_buses_csv():
    """Exporta la tabla de buses a CSV (solo admin)."""
    rows = [["ID", "Placa", "Conductor", "Descripcion", "Estado"]]
    for b in Bus.query.order_by(Bus.id.asc()).all():
        rows.append([b.id, b.plate, b.driver, b.description or "", b.status])
    logger.info("Export CSV buses solicitado por admin")
    return csv_response(rows, "buses.csv")
