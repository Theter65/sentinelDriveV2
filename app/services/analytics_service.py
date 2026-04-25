from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from math import ceil, floor
from statistics import mean, median, pstdev
from typing import Any

from app.extensions import db
from app.models.analytics import (
    AnalyticsRun,
    EventMagnitudeStatistic,
    EventTypeStatistic,
    HourlyEventStatistic,
    SpeedHistogramBin,
    VehicleStatisticsSummary,
)
from app.models.bus import Bus
from app.models.event import Event
from app.models.location import Location
from app.utils.time import ECUADOR_TZ, ecuador_now


DEFAULT_SPEED_LIMIT = 80.0
ICO_DESCRIPTION = (
    "Indicador estadistico descriptivo de criticidad operativa; no representa "
    "una prediccion de accidentes."
)
MAGNITUDE_EVENT_TYPES = (
    "Exceso de velocidad",
    "Frenado brusco",
    "Curva pronunciada",
    "Sobrecalentamiento",
)


def resolve_filter_values(
    source: Any,
    default_start: datetime | None = None,
    default_end: datetime | None = None,
) -> tuple[datetime, datetime, float]:
    """Normaliza filtros date_from, date_to y speed_limit para rutas y vistas."""

    now = ecuador_now()
    fallback_end = default_end or now
    fallback_start = default_start or (fallback_end - timedelta(days=30))

    date_from = _parse_datetime_filter(_get_filter(source, "date_from"), fallback_start, end_of_day=False)
    date_to = _parse_datetime_filter(_get_filter(source, "date_to"), fallback_end, end_of_day=True)
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    speed_limit = _safe_float(_get_filter(source, "speed_limit"), DEFAULT_SPEED_LIMIT)
    if speed_limit <= 0:
        speed_limit = DEFAULT_SPEED_LIMIT

    return date_from, date_to, speed_limit


def build_analytics_payload(
    bus_id: int | None,
    date_from: datetime,
    date_to: datetime,
    speed_limit: float,
) -> dict:
    """Construye la capa descriptiva sin modificar datos historicos."""

    bus = db.session.get(Bus, bus_id) if bus_id is not None else None
    if bus_id is not None and bus is None:
        raise LookupError("Bus no encontrado")

    location_query = Location.query.filter(Location.timestamp.between(date_from, date_to))
    event_query = Event.query.filter(Event.timestamp.between(date_from, date_to))
    if bus_id is not None:
        location_query = location_query.filter(Location.bus_id == bus_id)
        event_query = event_query.filter(Event.bus_id == bus_id)

    locations = location_query.order_by(Location.timestamp.asc()).all()
    events = event_query.order_by(Event.timestamp.asc()).all()

    speeds = [_clean_speed(location.speed) for location in locations]
    speeds = [speed for speed in speeds if speed is not None]

    event_rows = _build_event_type_rows(events)
    hourly_rows = _build_hourly_rows(events)
    magnitude_rows = _build_magnitude_rows(events)
    speed_histogram = _build_speed_histogram(speeds)
    speed_summary = _build_speed_summary(speeds, speed_limit)

    total_events = len(events)
    most_frequent_event = event_rows[0]["event_type"] if event_rows else None
    peak_event_hour = _peak_event_hour(hourly_rows)

    ico_score = _calculate_ico_score(
        total_events=total_events,
        speeding_percentage=speed_summary["speeding_percentage"],
        speed_cv=speed_summary["speed_cv"],
        magnitude_rows=magnitude_rows,
        speed_limit=speed_limit,
    )
    ico_level = _ico_level(ico_score)

    summary = {
        "bus_id": bus_id,
        "date_from": _iso(date_from),
        "date_to": _iso(date_to),
        "total_locations": len(locations),
        "valid_speed_samples": len(speeds),
        "total_events": total_events,
        **speed_summary,
        "ico_score": ico_score,
        "ico_level": ico_level,
        "ico_description": ICO_DESCRIPTION,
    }

    return {
        "analytics_run_id": None,
        "status": "calculated",
        "source": "calculated",
        "generated_at": _iso(ecuador_now()),
        "bus": _bus_payload(bus),
        "filters": {
            "bus_id": bus_id,
            "date_from": _iso(date_from),
            "date_to": _iso(date_to),
            "speed_limit": _round(speed_limit),
        },
        "summary": summary,
        "events_by_type": event_rows,
        "events_by_hour": hourly_rows,
        "speed_histogram": speed_histogram,
        "event_magnitudes": magnitude_rows,
        "derived": {
            "most_frequent_event": most_frequent_event,
            "peak_event_hour": peak_event_hour,
        },
    }


def generate_analytics_run(
    bus_id: int,
    date_from: datetime,
    date_to: datetime,
    speed_limit: float,
    notes: str | None = None,
) -> dict:
    """Calcula y persiste una ejecucion analitica nueva para un vehiculo."""

    payload = build_analytics_payload(bus_id, date_from, date_to, speed_limit)

    try:
        analytics_run = AnalyticsRun(
            bus_id=bus_id,
            date_from=date_from,
            date_to=date_to,
            speed_limit=speed_limit,
            status="completed",
            notes=notes,
        )
        db.session.add(analytics_run)
        db.session.flush()

        summary = payload["summary"]
        db.session.add(
            VehicleStatisticsSummary(
                analytics_run_id=analytics_run.id,
                bus_id=bus_id,
                date_from=date_from,
                date_to=date_to,
                total_locations=summary["total_locations"],
                total_events=summary["total_events"],
                speed_min=summary["speed_min"],
                speed_max=summary["speed_max"],
                speed_avg=summary["speed_avg"],
                speed_median=summary["speed_median"],
                speed_p85=summary["speed_p85"],
                speed_p95=summary["speed_p95"],
                speed_stddev=summary["speed_stddev"],
                speed_cv=summary["speed_cv"],
                speeding_count=summary["speeding_count"],
                speeding_percentage=summary["speeding_percentage"],
                ico_score=summary["ico_score"],
                ico_level=summary["ico_level"],
            )
        )

        for row in payload["events_by_type"]:
            db.session.add(
                EventTypeStatistic(
                    analytics_run_id=analytics_run.id,
                    event_type=row["event_type"],
                    event_count=row["event_count"],
                    event_percentage=row["event_percentage"],
                )
            )

        for row in payload["events_by_hour"]:
            db.session.add(
                HourlyEventStatistic(
                    analytics_run_id=analytics_run.id,
                    hour=row["hour"],
                    total_events=row["total_events"],
                )
            )

        for row in payload["speed_histogram"]:
            db.session.add(
                SpeedHistogramBin(
                    analytics_run_id=analytics_run.id,
                    bin_start=row["bin_start"],
                    bin_end=row["bin_end"],
                    frequency=row["frequency"],
                    percentage=row["percentage"],
                )
            )

        for row in payload["event_magnitudes"]:
            db.session.add(
                EventMagnitudeStatistic(
                    analytics_run_id=analytics_run.id,
                    event_type=row["event_type"],
                    max_value=row["max_value"],
                    avg_value=row["avg_value"],
                    count=row["count"],
                )
            )

        db.session.commit()
        payload["analytics_run_id"] = analytics_run.id
        payload["status"] = analytics_run.status
        payload["source"] = "persisted"
        payload["generated_at"] = _iso(analytics_run.generated_at)
        return payload
    except Exception:
        db.session.rollback()
        raise


def build_chart_data(payload: dict) -> dict:
    """Adaptador para Chart.js en la pantalla de reportes."""

    return {
        "event_type_labels": [row["event_type"] for row in payload["events_by_type"]],
        "event_type_data": [row["event_count"] for row in payload["events_by_type"]],
        "hour_labels": [f"{row['hour']:02d}:00" for row in payload["events_by_hour"]],
        "hour_data": [row["total_events"] for row in payload["events_by_hour"]],
        "speed_labels": [row["label"] for row in payload["speed_histogram"]],
        "speed_data": [row["frequency"] for row in payload["speed_histogram"]],
        "magnitude_labels": [row["event_type"] for row in payload["event_magnitudes"]],
        "magnitude_data": [row["max_value"] for row in payload["event_magnitudes"]],
        "ico_score": payload["summary"]["ico_score"],
        "ico_remainder": max(0, _round(100 - payload["summary"]["ico_score"])),
    }


def _build_speed_summary(speeds: list[float], speed_limit: float) -> dict:
    if not speeds:
        return {
            "speed_min": 0,
            "speed_max": 0,
            "speed_avg": 0,
            "speed_median": 0,
            "speed_p85": 0,
            "speed_p95": 0,
            "speed_stddev": 0,
            "speed_cv": 0,
            "speeding_count": 0,
            "speeding_percentage": 0,
        }

    sorted_speeds = sorted(speeds)
    avg_speed = mean(sorted_speeds)
    stddev = pstdev(sorted_speeds) if len(sorted_speeds) > 1 else 0
    speeding_count = sum(1 for speed in sorted_speeds if speed > speed_limit)

    return {
        "speed_min": _round(min(sorted_speeds)),
        "speed_max": _round(max(sorted_speeds)),
        "speed_avg": _round(avg_speed),
        "speed_median": _round(median(sorted_speeds)),
        "speed_p85": _round(_percentile(sorted_speeds, 85)),
        "speed_p95": _round(_percentile(sorted_speeds, 95)),
        "speed_stddev": _round(stddev),
        "speed_cv": _round((stddev / avg_speed) * 100) if avg_speed > 0 else 0,
        "speeding_count": speeding_count,
        "speeding_percentage": _round((speeding_count / len(sorted_speeds)) * 100),
    }


def _build_event_type_rows(events: list[Event]) -> list[dict]:
    total_events = len(events)
    counts = Counter(event.type for event in events if event.type)
    rows = []
    for event_type, event_count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        rows.append(
            {
                "event_type": event_type,
                "event_count": event_count,
                "event_percentage": _round((event_count / total_events) * 100) if total_events else 0,
            }
        )
    return rows


def _build_hourly_rows(events: list[Event]) -> list[dict]:
    counts = Counter(_event_hour(event.timestamp) for event in events if event.timestamp)
    return [{"hour": hour, "total_events": counts.get(hour, 0)} for hour in range(24)]


def _build_speed_histogram(speeds: list[float]) -> list[dict]:
    total = len(speeds)
    counts = defaultdict(int)
    for speed in speeds:
        bucket = 110 if speed >= 110 else int(speed // 10) * 10
        counts[bucket] += 1

    rows = []
    for bin_start in range(0, 111, 10):
        bin_end = None if bin_start == 110 else bin_start + 10
        frequency = counts.get(bin_start, 0)
        label = f"{bin_start}+" if bin_end is None else f"{bin_start}-{bin_end}"
        rows.append(
            {
                "bin_start": float(bin_start),
                "bin_end": float(bin_end) if bin_end is not None else None,
                "label": label,
                "frequency": frequency,
                "percentage": _round((frequency / total) * 100) if total else 0,
            }
        )
    return rows


def _build_magnitude_rows(events: list[Event]) -> list[dict]:
    values_by_type = defaultdict(list)
    for event in events:
        if event.type not in MAGNITUDE_EVENT_TYPES:
            continue
        value = _safe_float(event.value, None)
        if value is None:
            continue
        values_by_type[event.type].append(_magnitude_value(event.type, value))

    rows = []
    for event_type in MAGNITUDE_EVENT_TYPES:
        values = values_by_type.get(event_type, [])
        if not values:
            continue
        rows.append(
            {
                "event_type": event_type,
                "max_value": _round(max(values)),
                "avg_value": _round(mean(values)),
                "count": len(values),
            }
        )
    return rows


def _calculate_ico_score(
    total_events: int,
    speeding_percentage: float,
    speed_cv: float,
    magnitude_rows: list[dict],
    speed_limit: float,
) -> float:
    # ICO descriptivo:
    # 0.40 eventos + 0.30 exceso velocidad + 0.20 variabilidad + 0.10 magnitudes.
    # Cada componente se normaliza a 0-100 para evitar que una escala domine a las demas.
    events_normalized = _clamp((total_events / 50) * 100)
    speeding_normalized = _clamp(speeding_percentage)
    variability_normalized = _clamp((speed_cv / 60) * 100)
    magnitude_normalized = _normalize_event_magnitudes(magnitude_rows, speed_limit)

    return _round(
        (0.40 * events_normalized)
        + (0.30 * speeding_normalized)
        + (0.20 * variability_normalized)
        + (0.10 * magnitude_normalized)
    )


def _normalize_event_magnitudes(magnitude_rows: list[dict], speed_limit: float) -> float:
    normalized = []
    for row in magnitude_rows:
        event_type = row["event_type"]
        value = row["max_value"]
        if event_type == "Exceso de velocidad":
            baseline = max(speed_limit, 1)
            normalized.append(_clamp(((value - baseline) / baseline) * 100))
        elif event_type in ("Frenado brusco", "Curva pronunciada"):
            normalized.append(_clamp((abs(value) / 5) * 100))
        elif event_type == "Sobrecalentamiento":
            normalized.append(_clamp(((value - 80) / 40) * 100))

    return _round(mean(normalized)) if normalized else 0


def _ico_level(score: float) -> str:
    if score <= 25:
        return "Bajo"
    if score <= 50:
        return "Moderado"
    if score <= 75:
        return "Alto"
    return "Crítico"


def _peak_event_hour(hourly_rows: list[dict]) -> int | None:
    if not any(row["total_events"] for row in hourly_rows):
        return None
    return max(hourly_rows, key=lambda row: row["total_events"])["hour"]


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        return 0
    if len(sorted_values) == 1:
        return sorted_values[0]

    position = (len(sorted_values) - 1) * (percentile / 100)
    lower = floor(position)
    upper = ceil(position)
    if lower == upper:
        return sorted_values[int(position)]
    lower_weight = sorted_values[lower] * (upper - position)
    upper_weight = sorted_values[upper] * (position - lower)
    return lower_weight + upper_weight


def _event_hour(timestamp: datetime) -> int:
    if timestamp.tzinfo is None:
        return timestamp.hour
    return timestamp.astimezone(ECUADOR_TZ).hour


def _parse_datetime_filter(value: Any, fallback: datetime, end_of_day: bool) -> datetime:
    if not value:
        return _ensure_ecuador_timezone(fallback)

    raw_value = str(value).strip()
    try:
        if len(raw_value) == 10:
            parsed_date = datetime.fromisoformat(raw_value).date()
            parsed_time = time.max if end_of_day else time.min
            return datetime.combine(parsed_date, parsed_time, tzinfo=ECUADOR_TZ)
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        return _ensure_ecuador_timezone(parsed)
    except ValueError:
        return _ensure_ecuador_timezone(fallback)


def _ensure_ecuador_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=ECUADOR_TZ)
    return value.astimezone(ECUADOR_TZ)


def _clean_speed(value: Any) -> float | None:
    speed = _safe_float(value, None)
    if speed is None or speed < 0:
        return None
    return speed


def _safe_float(value: Any, default: float | None) -> float | None:
    try:
        if value is None:
            return default
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _magnitude_value(event_type: str, value: float) -> float:
    if event_type in ("Frenado brusco", "Curva pronunciada"):
        return abs(value)
    return value


def _bus_payload(bus: Bus | None) -> dict:
    if bus is None:
        return {"id": None, "plate": "Flota completa", "driver": None}
    return {"id": bus.id, "plate": bus.plate, "driver": bus.driver}


def _get_filter(source: Any, key: str):
    if hasattr(source, "get"):
        return source.get(key)
    return None


def _clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    return max(minimum, min(maximum, value))


def _round(value: float | int | None) -> float:
    if value is None:
        return 0
    return round(float(value), 2)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
