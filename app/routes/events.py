# app/routes/events.py - Listado de eventos y API de notificaciones
#
# Lista paginada de eventos críticos con filtros implícitos.
# Expone APIs JSON para polling de notificaciones en tiempo real:
# - /api/events/updates: devuelve eventos nuevos desde un ID
# - /api/events/count: conteo de eventos no vistos
# =============================================================================

from flask import Blueprint, jsonify, render_template, request
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
                "value": e.resolved_value,
                "value1": e.resolved_value1,
                "value2": e.value2,
                "value_label": e.value_label,
                "description": getattr(e, "description", None),
                "timestamp": e.timestamp.strftime("%Y-%m-%dT%H:%M:%S") if e.timestamp else None,
            }
        )

    # IDs validos de los ultimos 200 eventos (para que el frontend elimine los borrados)
    valid_ids = [
        row[0]
        for row in db.session.query(Event.id).order_by(Event.id.desc()).limit(200).all()
    ]

    return jsonify({"latest_id": latest_id, "events": payload, "valid_ids": valid_ids})


@events_bp.route("/api/events/count")
@login_required
def api_events_count():
    """Devuelve total de eventos recientes desde un ID de referencia."""
    after_id = request.args.get("after_id", default=0, type=int) or 0
    after_id = max(0, after_id)
    latest_id = db.session.query(func.max(Event.id)).scalar() or 0
    new_events_count = (
        db.session.query(func.count(Event.id))
        .filter(Event.id > after_id)
        .scalar()
        or 0
    )
    return jsonify({"total": new_events_count, "latest_id": latest_id})
