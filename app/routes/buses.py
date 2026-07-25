# app/routes/buses.py - CRUD de buses de la flota
#
# Permite listar, crear, editar y eliminar buses registrados.
# Solo usuarios admin pueden modificar/eliminar; usuarios con rol
# básico pueden consultar la lista. Incluye exportación CSV.
# =============================================================================

from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash

from app.decorators import login_required, require_admin
from app.extensions import db
from app.models.bus import Bus
from app.models.event import Event
from app.models.location import Location
from app.models.maintenance import Maintenance
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
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Error al registrar bus ID %s", bus_id)
            return render_template("add_bus.html", error="Error al guardar el bus")
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
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Error al editar bus ID %s", bus_id)
            return render_template("edit_bus.html", bus=bus, error="Error al guardar los cambios")
        logger.info("Bus editado: ID %s, placa %s, conductor %s", bus_id, bus.plate, bus.driver)
        return redirect(url_for("buses.buses"))
    return render_template("edit_bus.html", bus=bus)


@buses_bp.route("/bus/delete/<int:bus_id>", methods=["POST"])
@require_admin
def delete_bus(bus_id):
    """Eliminar un bus y toda su informacion asociada."""
    bus = Bus.query.get_or_404(bus_id)
    plate = bus.plate
    try:
        # Eliminar registros dependientes antes de borrar el bus
        Location.query.filter_by(bus_id=bus_id).delete(synchronize_session=False)
        Maintenance.query.filter_by(bus_id=bus_id).delete(synchronize_session=False)
        db.session.delete(bus)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Error al eliminar bus ID %s", bus_id)
        flash("Error al eliminar el bus.", "danger")
        return redirect(url_for("buses.buses"))
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


@buses_bp.route("/bus/<int:bus_id>/delete-events", methods=["POST"])
@require_admin
def delete_bus_events(bus_id):
    """Eliminar eventos de un bus por tipo y/o rango de fechas."""
    bus = Bus.query.get_or_404(bus_id)

    event_type = (request.form.get("event_type") or "").strip()
    date_from = (request.form.get("date_from") or "").strip()
    date_to = (request.form.get("date_to") or "").strip()

    query = Event.query.filter_by(bus_id=bus_id)

    if event_type:
        query = query.filter_by(type=event_type)

    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Event.timestamp >= dt_from)
        except ValueError:
            flash("Fecha desde invalida.", "danger")
            return redirect(url_for("buses.buses"))

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            query = query.filter(Event.timestamp <= dt_to)
        except ValueError:
            flash("Fecha hasta invalida.", "danger")
            return redirect(url_for("buses.buses"))

    count = query.count()
    if count == 0:
        flash("No se encontraron eventos con esos filtros.", "warning")
        return redirect(url_for("buses.buses"))

    query.delete(synchronize_session=False)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Error al eliminar eventos del bus %s", bus.plate)
        flash("Error al eliminar los eventos.", "danger")
        return redirect(url_for("buses.buses"))
    logger.info("Eventos eliminados bus %s: %d registros (tipo=%s, desde=%s, hasta=%s)",
                bus.plate, count, event_type or "todos", date_from or "sin limite", date_to or "sin limite")
    flash(f"Se eliminaron {count} eventos del bus {bus.plate}.", "success")
    return redirect(url_for("buses.buses"))


@buses_bp.route("/bus/<int:bus_id>/delete-locations", methods=["POST"])
@require_admin
def delete_bus_locations(bus_id):
    """Eliminar ubicaciones GPS de un bus por rango de fechas."""
    bus = Bus.query.get_or_404(bus_id)

    date_from = (request.form.get("date_from") or "").strip()
    date_to = (request.form.get("date_to") or "").strip()

    query = Location.query.filter_by(bus_id=bus_id)

    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Location.timestamp >= dt_from)
        except ValueError:
            flash("Fecha desde invalida.", "danger")
            return redirect(url_for("buses.buses"))

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            query = query.filter(Location.timestamp <= dt_to)
        except ValueError:
            flash("Fecha hasta invalida.", "danger")
            return redirect(url_for("buses.buses"))

    count = query.count()
    if count == 0:
        flash("No se encontraron ubicaciones con esos filtros.", "warning")
        return redirect(url_for("buses.buses"))

    query.delete(synchronize_session=False)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Error al eliminar ubicaciones del bus %s", bus.plate)
        flash("Error al eliminar las ubicaciones.", "danger")
        return redirect(url_for("buses.buses"))
    logger.info("Ubicaciones eliminadas bus %s: %d registros (desde=%s, hasta=%s)",
                bus.plate, count, date_from or "sin limite", date_to or "sin limite")
    flash(f"Se eliminaron {count} ubicaciones del bus {bus.plate}.", "success")
    return redirect(url_for("buses.buses"))
