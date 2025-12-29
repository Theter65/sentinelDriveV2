from flask import Blueprint, render_template
from app.decorators import login_required
from app.extensions import db
from app.models.bus import Bus
from app.models.event import Event
from app.utils.logging import get_logger

logger = get_logger(__name__)

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    """Panel principal con métricas clave del sistema."""
    total_buses = Bus.query.count()
    total_events = Event.query.count()
    last_events = Event.query.order_by(Event.timestamp.desc()).limit(5).all()
    return render_template("dashboard.html",
                          total_buses=total_buses,
                          total_events=total_events,
                          last_events=last_events)