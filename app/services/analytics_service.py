# app/services/analytics_service.py - Motor de analítica descriptiva
#
# Implementa los cálculos estadísticos del módulo de analítica:
# - Resumen de velocidad (min, max, avg, percentiles, desviación)
# - Distribución de eventos por tipo y hora
# - Histograma de velocidad en rangos de 10 km/h
# - Magnitudes por tipo de evento
# - Matriz de intervención operativa (5 indicadores)
# - Índice ICO (Indicador de Criticidad Operativa)
#
# Todos los cálculos son descriptivos (no predictivos) y siguen
# criterios basados en normativa de seguridad vial.
# =============================================================================

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
    "Curva peligrosa",
    "Otros",
)
INTERVENTION_LEVELS = (
    "Aceptable",
    "Monitoreo",
    "Intervención correctiva",
    "Intervención prioritaria",
)


# ── Filtros y entrada ────────────────────────────────────────────────────────

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


# ── Construcción del payload analítico ──────────────────────────────────────

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
    intervention_summary = _build_intervention_summary(
        speed_summary=speed_summary,
        events=events,
        event_rows=event_rows,
        hourly_rows=hourly_rows,
        magnitude_rows=magnitude_rows,
        speed_limit=speed_limit,
    )

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
        "intervention_summary": intervention_summary,
        "derived": {
            "most_frequent_event": most_frequent_event,
            "peak_event_hour": peak_event_hour,
        },
    }


# ── Persistencia de ejecuciones analíticas ──────────────────────────────────

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


# ── Adaptador para gráficos Chart.js ────────────────────────────────────────

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
    }


# ── Cálculos estadísticos internos ──────────────────────────────────────────

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
        value = _safe_float(_event_primary_value(event), None)
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
                "unit": _event_unit(event_type),
            }
        )
    return rows


# ── Matriz de intervención operativa ────────────────────────────────────────

def _build_intervention_summary(
    speed_summary: dict,
    events: list[Event],
    event_rows: list[dict],
    hourly_rows: list[dict],
    magnitude_rows: list[dict],
    speed_limit: float,
) -> dict:
    speed_indicator = _speeding_intervention(speed_summary, speed_limit)
    braking_indicator = _braking_intervention(events)
    curve_indicator = _curve_intervention(events)
    event_type_indicator = _event_type_intervention(event_rows)
    hourly_indicator = _hourly_intervention(hourly_rows)
    magnitude_indicator = _magnitude_intervention(magnitude_rows)
    indicators = [
        speed_indicator,
        braking_indicator,
        curve_indicator,
        event_type_indicator,
        hourly_indicator,
        magnitude_indicator,
    ]
    global_level = _worst_intervention_level(indicator["level"] for indicator in indicators)
    recommendations = _unique_non_empty(
        [indicator["recommendation"] for indicator in indicators]
        + [_global_intervention_recommendation(global_level)]
    )

    matrix = [
        _matrix_row("Velocidad", speed_indicator),
        _matrix_row("Frenado brusco", braking_indicator),
        _matrix_row("Curva peligrosa", curve_indicator),
        _matrix_row("Eventos por tipo", event_type_indicator),
        _matrix_row("Eventos por hora", hourly_indicator),
        _matrix_row("Magnitud de eventos", magnitude_indicator),
    ]

    return {
        "global_level": global_level,
        "global_level_key": _level_key(global_level),
        "global_recommendation": _global_intervention_recommendation(global_level),
        "speeding": speed_indicator,
        "braking": braking_indicator,
        "events": {
            "level": event_type_indicator["level"],
            "level_key": event_type_indicator["level_key"],
            "total_events": event_type_indicator["total_events"],
            "dominant_event": event_type_indicator["dominant_event"],
            "critical_hour": hourly_indicator["critical_hour"],
            "recommendation": event_type_indicator["recommendation"],
        },
        "event_types": event_type_indicator,
        "event_hours": hourly_indicator,
        "magnitudes": magnitude_indicator,
        "recommendations": recommendations,
        "matrix": matrix,
    }


def _speeding_intervention(speed_summary: dict, speed_limit: float) -> dict:
    max_speed = _round(speed_summary.get("speed_max", 0))
    max_excess = _round(max(0, max_speed - speed_limit))
    monitoring_threshold = _round(speed_limit + 5)
    corrective_threshold = _round(speed_limit * 1.10)
    priority_threshold = _round(speed_limit + 15)

    if max_speed >= priority_threshold:
        level = "Intervención prioritaria"
        threshold_used = f"Velocidad máxima >= {priority_threshold} km/h"
        recommendation = "Se recomienda intervención prioritaria por exceso severo de velocidad."
    elif max_speed >= corrective_threshold:
        level = "Intervención correctiva"
        threshold_used = f"Velocidad máxima >= {corrective_threshold} km/h (aprox. 10% sobre el límite)"
        recommendation = "Se recomienda intervención correctiva por superar aproximadamente el 10% del límite operativo configurado."
    elif max_speed > speed_limit or max_speed >= monitoring_threshold:
        level = "Monitoreo"
        threshold_used = f"Velocidad máxima > {speed_limit:g} km/h; monitoreo desde {monitoring_threshold:g} km/h"
        recommendation = "Se recomienda monitorear episodios de exceso de velocidad."
    else:
        level = "Aceptable"
        threshold_used = f"Velocidad máxima <= {speed_limit:g} km/h"
        recommendation = "Operación dentro del límite de velocidad configurado."

    return {
        "level": level,
        "level_key": _level_key(level),
        "max_speed": max_speed,
        "speed_limit": _round(speed_limit),
        "max_excess": max_excess,
        "threshold_used": threshold_used,
        "observed_value": f"{max_speed:g} km/h; exceso máximo {max_excess:g} km/h",
        "recommendation": recommendation,
        "methodological_source": "OMS, gestión de velocidad; umbrales operativos sobre límite.",
    }


def _braking_intervention(events: list[Event]) -> dict:
    values = [
        value
        for value in (_safe_float(_event_primary_value(event), None) for event in events if event.type == "Frenado brusco")
        if value is not None
    ]
    total_harsh_brakes = len(values)
    critical_count = sum(1 for value in values if value <= -3.92)
    moderate_count = sum(1 for value in values if value <= -3.0)
    severe_count = sum(1 for value in values if value <= -6.0)
    max_deceleration = _round(min(values)) if values else 0

    if severe_count or critical_count >= 2:
        level = "Intervención prioritaria"
        threshold_used = "value <= -6.0 m/s² o 2+ frenados críticos <= -3.92 m/s²"
        recommendation = "Se detectó un frenado muy severo o repetición de frenados críticos; se recomienda intervención prioritaria."
    elif critical_count:
        level = "Intervención correctiva"
        threshold_used = "value <= -3.92 m/s² (aprox. 0.4g)"
        recommendation = "Se detectaron frenados críticos; se recomienda revisar el patrón de conducción."
    elif moderate_count:
        level = "Monitoreo"
        threshold_used = "value <= -3.0 m/s²"
        recommendation = "Se detectaron frenados bruscos moderados; revisar anticipación y distancia de seguridad."
    elif total_harsh_brakes:
        level = "Monitoreo"
        threshold_used = "Evento de frenado brusco registrado sin superar umbral crítico"
        recommendation = "Se registraron frenados bruscos leves; mantener monitoreo del patrón de conducción."
    else:
        level = "Aceptable"
        threshold_used = "Sin frenados bruscos moderados o críticos"
        recommendation = "No se registraron frenados bruscos relevantes en el periodo seleccionado."

    return {
        "level": level,
        "level_key": _level_key(level),
        "total_harsh_brakes": total_harsh_brakes,
        "critical_harsh_brakes": critical_count,
        "max_deceleration": max_deceleration,
        "threshold_used": threshold_used,
        "observed_value": f"{total_harsh_brakes} frenados; más fuerte {max_deceleration:g} m/s²; críticos {critical_count}",
        "recommendation": recommendation,
        "methodological_source": "Hard braking 0.4g en estudios naturalísticos.",
    }


def _curve_intervention(events: list[Event]) -> dict:
    values = [
        value
        for value in (_safe_float(_event_primary_value(event), None) for event in events if event.type == "Curva peligrosa")
        if value is not None
    ]
    total_curves = len(values)
    severe_count = sum(1 for value in values if abs(value) >= 5.0)
    moderate_count = sum(1 for value in values if abs(value) >= 4.0)
    max_lateral = _round(max(values, key=abs)) if values else 0

    if severe_count:
        level = "Intervención prioritaria"
        threshold_used = "abs(value) >= 5.0 m/s²"
        recommendation = "Se detectaron curvas con aceleración lateral muy elevada; se recomienda intervención prioritaria."
    elif moderate_count >= 3:
        level = "Intervención correctiva"
        threshold_used = "abs(value) >= 4.0 m/s² recurrente (3+ veces)"
        recommendation = "Se detectaron múltiples curvas con aceleración lateral elevada; revisar trazado y velocidad en curvas."
    elif moderate_count:
        level = "Monitoreo"
        threshold_used = "abs(value) >= 4.0 m/s²"
        recommendation = "Se detectaron curvas con aceleración lateral significativa; mantener monitoreo."
    elif total_curves:
        level = "Monitoreo"
        threshold_used = "Evento de curva peligrosa registrado"
        recommendation = "Se registraron curvas peligrosas dentro de umbral aceptable."
    else:
        level = "Aceptable"
        threshold_used = "Sin curvas peligrosas registradas"
        recommendation = "No se registraron curvas peligrosas en el periodo seleccionado."

    return {
        "level": level,
        "level_key": _level_key(level),
        "total_curve_events": total_curves,
        "max_lateral_acceleration": max_lateral,
        "threshold_used": threshold_used,
        "observed_value": f"{total_curves} curvas; máxima lateral {max_lateral:g} m/s²; severas {severe_count}",
        "recommendation": recommendation,
        "methodological_source": "ISO 14793, NHTSA Rollover Stability para vehículos pesados.",
    }


def _event_type_intervention(event_rows: list[dict]) -> dict:
    total_events = sum(row["event_count"] for row in event_rows)
    dominant = event_rows[0] if event_rows else None
    dominant_event = dominant["event_type"] if dominant else None
    dominant_count = dominant["event_count"] if dominant else 0
    dominant_percentage = dominant["event_percentage"] if dominant else 0
    level = "Monitoreo" if total_events else "Aceptable"
    recommendation = _dominant_event_recommendation(dominant_event) if dominant_event else "No se registraron eventos operativos en el periodo seleccionado."

    return {
        "level": level,
        "level_key": _level_key(level),
        "total_events": total_events,
        "dominant_event": dominant_event,
        "dominant_count": dominant_count,
        "dominant_percentage": dominant_percentage,
        "threshold_used": "Identificación de evento dominante",
        "observed_value": (
            f"{dominant_event}: {dominant_count} eventos ({dominant_percentage:g}%)"
            if dominant_event
            else "Sin eventos"
        ),
        "recommendation": recommendation,
        "methodological_source": "Near-miss events modelados por tipo.",
    }


def _hourly_intervention(hourly_rows: list[dict]) -> dict:
    peak_hour = _peak_event_hour(hourly_rows)
    peak_count = 0
    if peak_hour is not None:
        peak_count = next((row["total_events"] for row in hourly_rows if row["hour"] == peak_hour), 0)
    level = "Monitoreo" if peak_count else "Aceptable"
    critical_hour = f"{peak_hour:02d}:00-{(peak_hour + 1) % 24:02d}:00" if peak_hour is not None else None
    recommendation = (
        "Se recomienda revisar la operación durante la hora con mayor concentración de eventos."
        if peak_count
        else "No se identificó una franja horaria con concentración de eventos."
    )

    return {
        "level": level,
        "level_key": _level_key(level),
        "critical_hour": critical_hour,
        "peak_event_hour": peak_hour,
        "peak_event_count": peak_count,
        "threshold_used": "Hora con mayor concentración de eventos",
        "observed_value": f"{critical_hour}: {peak_count} eventos" if critical_hour else "Sin concentración horaria",
        "recommendation": recommendation,
        "methodological_source": "Telemática operativa y análisis temporal de eventos.",
    }


def _magnitude_intervention(magnitude_rows: list[dict]) -> dict:
    main = _main_magnitude_row(magnitude_rows)
    if not main:
        return {
            "level": "Aceptable",
            "level_key": _level_key("Aceptable"),
            "main_magnitude_event": None,
            "max_value": 0,
            "unit": None,
            "threshold_used": "Sin magnitudes críticas registradas",
            "observed_value": "Sin magnitudes de eventos",
            "recommendation": "No se registraron magnitudes críticas en el periodo seleccionado.",
            "methodological_source": "Intensidad del evento según variable registrada.",
        }

    event_type = main["event_type"]
    recommendation = _magnitude_recommendation(event_type)
    return {
        "level": "Monitoreo",
        "level_key": _level_key("Monitoreo"),
        "main_magnitude_event": event_type,
        "max_value": main["max_value"],
        "unit": main.get("unit"),
        "threshold_used": "Magnitud máxima dentro de cada tipo; no compara unidades distintas",
        "observed_value": f"{event_type}: {main['max_value']:g} {main.get('unit') or ''}".strip(),
        "recommendation": recommendation,
        "methodological_source": "Intensidad del evento según variable registrada.",
    }


def _matrix_row(indicator: str, data: dict) -> dict:
    return {
        "indicator": indicator,
        "observed_value": data["observed_value"],
        "threshold_used": data["threshold_used"],
        "level": data["level"],
        "level_key": data.get("level_key") or _level_key(data["level"]),
        "recommendation": data["recommendation"],
    }


def _worst_intervention_level(levels) -> str:
    rank = {level: index for index, level in enumerate(INTERVENTION_LEVELS)}
    return max(levels, key=lambda level: rank.get(level, 0), default="Aceptable")


def _level_key(level: str) -> str:
    mapping = {
        "Aceptable": "acceptable",
        "Monitoreo": "monitoring",
        "Intervención correctiva": "corrective",
        "Intervención prioritaria": "priority",
    }
    return mapping.get(level, "monitoring")


def _global_intervention_recommendation(level: str) -> str:
    if level == "Intervención prioritaria":
        return "Atender primero los indicadores en nivel prioritario y registrar acciones de intervención operativa."
    if level == "Intervención correctiva":
        return "Programar revisión correctiva sobre los indicadores que superaron umbrales operativos."
    if level == "Monitoreo":
        return "Mantener monitoreo y revisar tendencias si los eventos se repiten en próximos periodos."
    return "Mantener operación y monitoreo regular bajo los criterios configurados."


def _dominant_event_recommendation(event_type: str | None) -> str:
    recommendations = {
        "Exceso de velocidad": "Los eventos predominantes están relacionados con velocidad; se recomienda reforzar el control del límite operativo.",
        "Frenado brusco": "Los eventos predominantes están relacionados con frenado; se recomienda revisar anticipación, distancia de seguridad y comportamiento del conductor.",
        "Curva peligrosa": "Los eventos predominantes están relacionados con curvas; se recomienda revisar conducción en tramos sinuosos.",
        "Otros": "Los eventos predominantes requieren revisión del sensor o componente reportado.",
    }
    return recommendations.get(event_type, "Se recomienda revisar el tipo de evento predominante en el periodo seleccionado.")


def _magnitude_recommendation(event_type: str) -> str:
    if event_type == "Exceso de velocidad":
        return "Se recomienda revisar el evento de mayor velocidad registrado en el periodo."
    if event_type == "Frenado brusco":
        return "Se recomienda revisar el evento de frenado de mayor intensidad registrado en el periodo."
    return "Se recomienda revisar la magnitud máxima dentro de su propio tipo de evento."


def _main_magnitude_row(magnitude_rows: list[dict]) -> dict | None:
    priority = {
        "Exceso de velocidad": 0,
        "Frenado brusco": 1,
        "Curva peligrosa": 2,
        "Otros": 3,
    }
    if not magnitude_rows:
        return None
    return sorted(magnitude_rows, key=lambda row: (priority.get(row["event_type"], 99), -row["count"]))[0]


def _unique_non_empty(items: list[str]) -> list[str]:
    seen = set()
    unique = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


# ── Índice ICO (Indicador de Criticidad Operativa) ──────────────────────────

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
        elif event_type in ("Frenado brusco", "Curva peligrosa"):
            normalized.append(_clamp((abs(value) / 5) * 100))

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


# ── Funciones auxiliares matemáticas ────────────────────────────────────────

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
    if event_type in ("Frenado brusco", "Curva peligrosa"):
        return abs(value)
    return value


def _event_primary_value(event: Event):
    return getattr(event, "resolved_value1", None) if event is not None else None


def _event_unit(event_type: str) -> str:
    units = {
        "Exceso de velocidad": "km/h",
        "Frenado brusco": "m/s²",
        "Curva peligrosa": "m/s²",
        "Otros": "según sensor",
    }
    return units.get(event_type, "según sensor")


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
