# app/routes/reports.py - Reportes, estadísticas y exportación CSV
#
# Renderiza reportes con filtros por período, bus y límite de velocidad.
# Incluye estadísticas agregadas de flota y por vehículo, histogramas,
# gráficos Chart.js, y exportación CSV de eventos y tablas seleccionadas.
# =============================================================================

from datetime import timedelta

from flask import Blueprint, render_template, request
from sqlalchemy import Integer, and_, case, cast, extract, func, or_

from app.decorators import login_required
from app.extensions import db
from app.models.bus import Bus
from app.models.event import Event
from app.models.location import Location
from app.models.maintenance import Maintenance
from app.services.analytics_service import (
    build_analytics_payload,
    build_chart_data as build_analytics_chart_data,
    resolve_filter_values,
)
from app.utils.csv_export import csv_response
from app.utils.logging import get_logger
from app.utils.time import ecuador_now


logger = get_logger(__name__)

reports_bp = Blueprint("reports", __name__)

# Períodos predefinidos para filtros de reportes
PERIODS = {
    "day": timedelta(days=1),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
    "6months": timedelta(days=180),
    "year": timedelta(days=365),
}


# ── Filtros de tiempo y helper functions ─────────────────────────────────────

def get_time_filter(period):
    """Convierte un periodo textual en rango de fechas."""
    now = ecuador_now()
    delta = PERIODS.get(period, PERIODS["month"])
    return now - delta, now


def get_report_filter_values():
    """Normaliza filtros de reporte desde la solicitud."""
    selected_period = request.args.get("period", "month")
    default_start, default_end = get_time_filter(selected_period)
    start_time, end_time, speed_limit = resolve_filter_values(
        request.args,
        default_start=default_start,
        default_end=default_end,
    )
    return selected_period, start_time, end_time, speed_limit


def get_download_tables_filters(source):
    """Normaliza filtros para exportacion selectiva de tablas."""
    selected_period = source.get("period", "month")
    default_start, default_end = get_time_filter(selected_period)
    start_time, end_time, _ = resolve_filter_values(
        source,
        default_start=default_start,
        default_end=default_end,
    )
    selected_bus_id = source.get("bus_id", type=int)
    selected_event_type = (source.get("event_type") or "").strip()
    search_term = (source.get("search") or "").strip()
    return {
        "selected_period": selected_period,
        "start_time": start_time,
        "end_time": end_time,
        "selected_bus_id": selected_bus_id,
        "selected_event_type": selected_event_type,
        "search_term": search_term,
    }


# ── Estadísticas de velocidad ───────────────────────────────────────────────

def get_speed_stats(*filters):
    """Calcula estadisticas basicas de velocidad."""
    query = db.session.query(
        func.avg(Location.speed),
        func.max(Location.speed),
        func.min(Location.speed),
    ).filter(*filters)
    avg_speed, max_speed, min_speed = query.one()
    min_speed = (
        db.session.query(func.min(Location.speed))
        .filter(*filters, Location.speed > 0)
        .scalar()
    )
    return {
        "avg_speed": avg_speed or 0,
        "max_speed": max_speed or 0,
        "min_speed": min_speed or 0,
    }


def get_speed_histogram(*filters):
    """Agrupa velocidades en intervalos de 10 km/h."""
    bucket = cast(Location.speed / 10, Integer) * 10
    rows = (
        db.session.query(bucket.label("bucket"), func.count(Location.id))
        .filter(*filters, Location.speed.isnot(None), Location.speed >= 0)
        .group_by("bucket")
        .order_by("bucket")
        .all()
    )
    if not rows:
        return {"bins": [], "data": []}

    counts_by_bucket = {int(row[0]): row[1] for row in rows}
    max_bucket = max(counts_by_bucket)
    bins = list(range(0, max_bucket + 10, 10))
    data = [counts_by_bucket.get(bucket_value, 0) for bucket_value in bins]
    return {"bins": bins, "data": data}


# ── Estadísticas de eventos ─────────────────────────────────────────────────

def get_events_by_type(*filters):
    """Cuenta eventos por categoria."""
    return (
        db.session.query(Event.type, func.count(Event.id))
        .filter(*filters)
        .group_by(Event.type)
        .all()
    )


def get_events_by_hour(*filters):
    """Cuenta eventos por hora del dia."""
    return (
        db.session.query(
            extract("hour", Event.timestamp).label("hour"),
            func.count(Event.id),
        )
        .filter(*filters)
        .group_by("hour")
        .order_by("hour")
        .all()
    )


def get_bus_events_table(start_time, end_time):
    """Construye tabla de eventos por bus para la flota."""
    return (
        db.session.query(
            Bus.plate,
            func.count(Event.id).label("total_events"),
            func.sum(case((Event.type == "Frenado brusco", 1), else_=0)).label("frenado_brusco"),
            func.sum(case((Event.type == "Exceso de velocidad", 1), else_=0)).label("exceso_velocidad"),
            func.sum(case((Event.type == "Curva peligrosa", 1), else_=0)).label("curva_peligrosa"),
            func.sum(case((Event.type == "Otros", 1), else_=0)).label("otros"),
        )
        .outerjoin(
            Event,
            and_(Bus.id == Event.bus_id, Event.timestamp.between(start_time, end_time)),
        )
        .group_by(Bus.id, Bus.plate)
        .order_by(Bus.plate.asc())
        .all()
    )


def get_maintenance_by_driver(start_time, end_time):
    """Resume mantenimientos por conductor."""
    driver_rows = (
        db.session.query(
            Bus.driver.label("driver"),
            func.count(Maintenance.id).label("total_maintenances"),
            func.max(Maintenance.date).label("ultimo_mantenimiento"),
        )
        .join(Maintenance, Bus.id == Maintenance.bus_id)
        .filter(Maintenance.date.between(start_time, end_time))
        .group_by(Bus.driver)
        .order_by(Bus.driver.asc())
        .all()
    )

    results = []
    for row in driver_rows:
        latest_status = (
            db.session.query(Maintenance.status)
            .join(Bus, Bus.id == Maintenance.bus_id)
            .filter(
                Bus.driver == row.driver,
                Maintenance.date == row.ultimo_mantenimiento,
            )
            .order_by(Maintenance.id.desc())
            .scalar()
        )
        results.append(
            {
                "driver": row.driver,
                "total_maintenances": row.total_maintenances,
                "ultimo_mantenimiento": row.ultimo_mantenimiento,
                "estado_reciente": latest_status,
            }
        )
    return results


# ── Construcción de estadísticas agregadas e individuales ──────────────────

def build_group_stats(start_time, end_time, speed_limit):
    """Construye estadisticas agregadas para toda la flota."""
    event_filter = Event.timestamp.between(start_time, end_time)
    events_by_type = get_events_by_type(event_filter)
    events_by_hour = get_events_by_hour(event_filter)
    analytics = build_analytics_payload(None, start_time, end_time, speed_limit)
    summary = analytics["summary"]
    return {
        "total_events": sum(row[1] for row in events_by_type),
        "events_by_type": events_by_type,
        "events_by_hour": events_by_hour,
        "avg_speed": summary["speed_avg"],
        "max_speed": summary["speed_max"],
        "min_speed": summary["speed_min"],
        "analytics": analytics,
        "summary": summary,
        "bus_events_table": get_bus_events_table(start_time, end_time),
        "maintenance_by_driver": get_maintenance_by_driver(start_time, end_time),
    }


def build_individual_stats(selected_bus_id, start_time, end_time, speed_limit):
    """Construye estadisticas para un bus seleccionado."""
    bus = Bus.query.get_or_404(selected_bus_id)
    event_filters = [
        Event.bus_id == selected_bus_id,
        Event.timestamp.between(start_time, end_time),
    ]
    events_by_type = get_events_by_type(*event_filters)
    events_by_hour = get_events_by_hour(*event_filters)
    analytics = build_analytics_payload(selected_bus_id, start_time, end_time, speed_limit)
    summary = analytics["summary"]
    individual_stats = {
        "bus": bus,
        "total_events": sum(row[1] for row in events_by_type),
        "events_by_type": events_by_type,
        "events_by_hour": events_by_hour,
        "avg_speed": summary["speed_avg"],
        "max_speed": summary["speed_max"],
        "min_speed": summary["speed_min"],
        "analytics": analytics,
        "summary": summary,
    }
    return individual_stats, build_analytics_chart_data(analytics)


# ── Vistas principales ──────────────────────────────────────────────────────

@reports_bp.route("/reports")
@login_required
def reports():
    """Renderiza filtros, analitica y tablas de reportes."""
    selected_bus_id = request.args.get("bus_id", type=int)
    selected_period, start_time, end_time, selected_speed_limit = get_report_filter_values()
    buses = Bus.query.order_by(Bus.plate.asc()).all()

    group_stats = build_group_stats(start_time, end_time, selected_speed_limit)
    group_chart_data = build_analytics_chart_data(group_stats["analytics"])

    individual_stats = None
    individual_chart_data = None
    if selected_bus_id:
        individual_stats, individual_chart_data = build_individual_stats(
            selected_bus_id,
            start_time,
            end_time,
            selected_speed_limit,
        )

    return render_template(
        "reports.html",
        buses=buses,
        group_stats=group_stats,
        individual_stats=individual_stats,
        group_chart_data=group_chart_data,
        individual_chart_data=individual_chart_data,
        selected_period=selected_period,
        selected_bus_id=selected_bus_id,
        selected_speed_limit=selected_speed_limit,
        date_from_value=start_time.date().isoformat(),
        date_to_value=end_time.date().isoformat(),
    )


# ── Exportación CSV ─────────────────────────────────────────────────────────

@reports_bp.route("/reports/download_csv")
@login_required
def download_csv():
    """Exporta eventos filtrados a CSV."""
    selected_period, start_time, end_time, _speed_limit = get_report_filter_values()
    selected_bus_id = request.args.get("bus_id", type=int)
    rows = []

    if selected_bus_id:
        bus = Bus.query.get_or_404(selected_bus_id)
        rows.extend([
            [f"Vehiculo: {bus.plate}"],
            ["Periodo:", selected_period],
            ["Rango:", start_time, end_time],
            [],
            ["ID", "Tipo", "Value", "Value1", "Value2", "Fecha/Hora", "Latitud", "Longitud", "Descripcion"],
        ])
        events = Event.query.filter(
            Event.bus_id == selected_bus_id,
            Event.timestamp.between(start_time, end_time),
        ).order_by(Event.timestamp.asc(), Event.id.asc()).all()
        for event in events:
            rows.append(
                [
                    event.id,
                    event.type,
                    event.resolved_value,
                    event.resolved_value1,
                    event.value2,
                    event.timestamp,
                    event.latitude,
                    event.longitude,
                    getattr(event, "description", None),
                ]
            )
    else:
        rows.extend([
            ["Flota completa"],
            ["Periodo:", selected_period],
            ["Rango:", start_time, end_time],
            [],
            ["ID", "Bus ID", "Tipo", "Value", "Value1", "Value2", "Fecha/Hora", "Latitud", "Longitud", "Descripcion"],
        ])
        events = Event.query.filter(Event.timestamp.between(start_time, end_time)).order_by(Event.timestamp.asc(), Event.id.asc()).all()
        for event in events:
            rows.append(
                [
                    event.id,
                    event.bus_id,
                    event.type,
                    event.resolved_value,
                    event.resolved_value1,
                    event.value2,
                    event.timestamp,
                    event.latitude,
                    event.longitude,
                    getattr(event, "description", None),
                ]
            )

    return csv_response(rows, f"reportes_{selected_period}.csv")


@reports_bp.route("/reports/download_tables", methods=["GET", "POST"])
@login_required
def download_tables():
    """Exporta tablas seleccionadas a CSV consolidado."""
    """Exporta tablas seleccionadas a CSV consolidado."""
    buses = Bus.query.order_by(Bus.plate.asc()).all()
    event_types = [
        row[0]
        for row in db.session.query(Event.type)
        .filter(Event.type.isnot(None))
        .group_by(Event.type)
        .order_by(Event.type.asc())
        .all()
    ]

    if request.method == "POST":
        selected_tables = request.form.getlist("tables")
        filters = get_download_tables_filters(request.form)
        selected_period = filters["selected_period"]
        start_time = filters["start_time"]
        end_time = filters["end_time"]
        selected_bus_id = filters["selected_bus_id"]
        selected_event_type = filters["selected_event_type"]
        search_term = filters["search_term"]

        rows = [
            ["SENTNLDRIVE - Tablas seleccionadas"],
            ["Periodo:", selected_period],
            ["Rango:", start_time, end_time],
            ["Bus ID:", selected_bus_id if selected_bus_id else "Todos"],
            ["Tipo de evento:", selected_event_type or "Todos"],
            ["Busqueda:", search_term or "Sin filtro"],
            [],
        ]

        for table in selected_tables:
            rows.append([f"Tabla: {table.upper()}"])
            rows.append([])

            if table == "bus":
                rows.append(["ID", "Placa", "Conductor", "Descripcion", "Estado"])
                bus_query = Bus.query
                if selected_bus_id:
                    bus_query = bus_query.filter(Bus.id == selected_bus_id)
                if search_term:
                    like = f"%{search_term}%"
                    bus_query = bus_query.filter(
                        or_(
                            Bus.plate.ilike(like),
                            Bus.driver.ilike(like),
                            Bus.description.ilike(like),
                            cast(Bus.id, db.String).ilike(like),
                        )
                    )
                for bus in bus_query.order_by(Bus.id.asc()).all():
                    rows.append([bus.id, bus.plate, bus.driver, bus.description, bus.status])

            elif table == "event":
                rows.append(["ID", "Bus ID", "Tipo", "Value", "Value1", "Value2", "Fecha/Hora", "Latitud", "Longitud", "Descripcion"])
                event_query = Event.query.filter(Event.timestamp.between(start_time, end_time))
                if selected_bus_id:
                    event_query = event_query.filter(Event.bus_id == selected_bus_id)
                if selected_event_type:
                    event_query = event_query.filter(Event.type == selected_event_type)
                if search_term:
                    like = f"%{search_term}%"
                    event_query = event_query.join(Bus, Bus.id == Event.bus_id).filter(
                        or_(
                            Bus.plate.ilike(like),
                            Bus.driver.ilike(like),
                            Event.type.ilike(like),
                            Event.description.ilike(like),
                        )
                    )
                for event in event_query.order_by(Event.timestamp.asc(), Event.id.asc()).all():
                    rows.append(
                        [
                            event.id,
                            event.bus_id,
                            event.type,
                            event.resolved_value,
                            event.resolved_value1,
                            event.value2,
                            event.timestamp,
                            event.latitude,
                            event.longitude,
                            getattr(event, "description", None),
                        ]
                    )

            elif table == "maintenance":
                rows.append(["ID", "Bus ID", "Descripcion", "Fecha", "Estado"])
                maintenance_query = Maintenance.query.filter(Maintenance.date.between(start_time, end_time))
                if selected_bus_id:
                    maintenance_query = maintenance_query.filter(Maintenance.bus_id == selected_bus_id)
                if search_term:
                    like = f"%{search_term}%"
                    maintenance_query = maintenance_query.join(Bus, Bus.id == Maintenance.bus_id).filter(
                        or_(
                            Bus.plate.ilike(like),
                            Bus.driver.ilike(like),
                            Maintenance.description.ilike(like),
                        )
                    )
                for maintenance in maintenance_query.order_by(Maintenance.date.asc(), Maintenance.id.asc()).all():
                    rows.append([maintenance.id, maintenance.bus_id, maintenance.description, maintenance.date, maintenance.status])

            elif table == "location":
                rows.append(["ID", "Bus ID", "Latitud", "Longitud", "Velocidad", "Fecha/Hora"])
                location_query = Location.query.filter(Location.timestamp.between(start_time, end_time))
                if selected_bus_id:
                    location_query = location_query.filter(Location.bus_id == selected_bus_id)
                if search_term:
                    like = f"%{search_term}%"
                    location_query = location_query.join(Bus, Bus.id == Location.bus_id).filter(
                        or_(
                            Bus.plate.ilike(like),
                            Bus.driver.ilike(like),
                            cast(Location.bus_id, db.String).ilike(like),
                        )
                    )
                for location in location_query.order_by(Location.timestamp.asc(), Location.id.asc()).all():
                    rows.append([location.id, location.bus_id, location.lat, location.lon, location.speed, location.timestamp])

            rows.append([])

        if not selected_tables:
            rows.append(["No se seleccionaron tablas."])

        return csv_response(rows, f"tables_{selected_period}.csv")

    filters = get_download_tables_filters(request.args)
    return render_template(
        "download_tables.html",
        selected_period=filters["selected_period"],
        date_from_value=filters["start_time"].date().isoformat(),
        date_to_value=filters["end_time"].date().isoformat(),
        selected_bus_id=filters["selected_bus_id"],
        selected_event_type=filters["selected_event_type"],
        search_term=filters["search_term"],
        buses=buses,
        event_types=event_types,
    )
