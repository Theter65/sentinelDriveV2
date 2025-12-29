from flask import Blueprint, render_template, request, redirect, url_for
from app.decorators import login_required, require_admin
from app.extensions import db
from app.models.bus import Bus
from app.models.location import Location
from app.models.event import Event
from app.models.maintenance import Maintenance
from app.utils.logging import get_logger

logger = get_logger(__name__)

buses_bp = Blueprint('buses', __name__)

@buses_bp.route("/buses")
@login_required
def buses():
    """Lista de todos los buses registrados."""
    buses_list = Bus.query.all()
    return render_template("buses.html", buses=buses_list)

@buses_bp.route("/add_bus", methods=["GET", "POST"])
@require_admin
def add_bus():
    """Formulario para registrar un nuevo bus."""
    if request.method == "POST":
        bus_id = request.form.get("id")
        plate = request.form.get("plate")
        driver = request.form.get("driver")
        try:
            bus_id = int(bus_id)
        except (ValueError, TypeError):
            return render_template("add_bus.html", error="ID inválido (debe ser número)")
        if Bus.query.get(bus_id):
            return render_template("add_bus.html", error="El ID ya existe")
        new_bus = Bus(id=bus_id, plate=plate, driver=driver, status="Activo")
        db.session.add(new_bus)
        db.session.commit()
        logger.info(f"Bus registrado: ID {bus_id}, placa {plate}")
        return redirect(url_for("buses.buses"))
    return render_template("add_bus.html")

@buses_bp.route("/bus/edit/<int:bus_id>", methods=["GET", "POST"])
@require_admin
def edit_bus(bus_id):
    """Editar placa, conductor y estado de un bus existente."""
    bus = Bus.query.get_or_404(bus_id)
    if request.method == "POST":
        bus.plate = request.form.get("plate").strip()
        bus.driver = request.form.get("driver").strip()
        bus.status = request.form.get("status")
        db.session.commit()
        logger.info(f"Bus editado exitosamente: ID {bus_id}, placa {bus.plate}, conductor {bus.driver}")
        return redirect(url_for("buses.buses"))
    return render_template("edit_bus.html", bus=bus)

@buses_bp.route("/bus/delete/<int:bus_id>", methods=["POST"])
@require_admin
def delete_bus(bus_id):
    """Eliminar un bus y TODA su información asociada."""
    bus = Bus.query.get_or_404(bus_id)
    plate = bus.plate
    Location.query.filter_by(bus_id=bus_id).delete()
    Event.query.filter_by(bus_id=bus_id).delete()
    Maintenance.query.filter_by(bus_id=bus_id).delete()
    db.session.delete(bus)
    db.session.commit()
    logger.info(f"Bus eliminado completamente: ID {bus_id}, placa {plate}")
    return redirect(url_for("buses.buses"))