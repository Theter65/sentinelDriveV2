from sqlalchemy.orm import joinedload

from flask import Blueprint, render_template

from app.decorators import login_required
from app.models.event import Event
from app.utils.logging import get_logger


logger = get_logger(__name__)

events_bp = Blueprint("events", __name__)


@events_bp.route("/events")
@login_required
def events():
    """Lista de eventos criticos registrados."""
    all_events = (
        Event.query.options(joinedload(Event.bus))
        .order_by(Event.timestamp.desc())
        .limit(200)
        .all()
    )
    return render_template("events.html", events=all_events)
