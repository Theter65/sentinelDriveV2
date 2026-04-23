from flask import Blueprint, jsonify, render_template, request, session
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.decorators import login_required
from app.extensions import db
from app.models.event import Event
from app.utils.logging import get_logger


logger = get_logger(__name__)

events_bp = Blueprint("events", __name__)


@events_bp.route("/events")
@login_required
def events():
    """Lista paginada de eventos criticos."""
    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=50, type=int)
    per_page = max(10, min(per_page, 200))
    page = max(1, page)

    query = Event.query.options(joinedload(Event.bus)).order_by(Event.timestamp.desc())
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page + 1).all()
    has_next = len(items) > per_page
    items = items[:per_page]
    has_prev = page > 1

    latest_id = db.session.query(func.max(Event.id)).scalar() or 0
    session['events_last_seen_id'] = latest_id
    session.modified = True

    return render_template(
        "events.html",
        events=items,
        page=page,
        per_page=per_page,
        total=total,
        has_next=has_next,
        has_prev=has_prev,
    )


@events_bp.route("/api/events/updates")
@login_required
def api_event_updates():
    """Devuelve eventos nuevos para notificaciones (polling)."""
    after_id = request.args.get("after_id", default=0, type=int) or 0
    limit = max(1, min(request.args.get("limit", default=10, type=int), 30))

    latest_id = db.session.query(func.max(Event.id)).scalar() or 0

    events = (
        db.session.query(Event)
        .options(joinedload(Event.bus))
        .filter(Event.id > after_id)
        .order_by(Event.id.asc())
        .limit(limit)
        .all()
    )

    payload = []
    for e in events:
        payload.append(
            {
                "id": e.id,
                "bus_id": e.bus_id,
                "plate": e.bus.plate if e.bus else None,
                "type": e.type,
                "value": e.value,
                "description": getattr(e, "description", None),
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            }
        )

    return jsonify({"latest_id": latest_id, "events": payload})


@events_bp.route("/api/events/count")
@login_required
def api_events_count():
    """Devuelve el total de eventos nuevos desde la ultima visita."""
    latest_id = db.session.query(func.max(Event.id)).scalar() or 0
    last_seen_id = session.get('events_last_seen_id', 0)
    new_events_count = max(0, latest_id - last_seen_id)
    return jsonify({"total": new_events_count, "latest_id": latest_id})
