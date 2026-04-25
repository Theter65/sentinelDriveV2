import csv
import io
from datetime import timedelta

from flask import Blueprint, Response, render_template, request
from sqlalchemy import Integer, and_, case, cast, extract, func

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
from app.utils.logging import get_logger
from app.utils.time import ecuador_now


logger = get_logger(__name__)

reports_bp = Blueprint("reports", __name__)

PERIODS = {
    "day": timedelta(days=1),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
    "6months": timedelta(days=180),
    "year": timedelta(days=365),
}


def get_time_filter(period):
    now = ecuador_now()
    delta = PERIODS.get(period, PERIODS["month"])
    return now - delta, now


def get_report_filter_values():
    selected_period = request.args.get("period", "month")
    default_start, default_end = get_time_filter(selected_period)
    start_time, end_time, speed_limit = resolve_filter_values(
        request.args,
        default_start=default_start,
        default_end=default_end,
    )
    return selected_period, start_time, end_time, speed_limit


def get_speed_stats(*filters):
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


def get_events_by_type(*filters):
    return (
        db.session.query(Event.type, func.count(Event.id))
        .filter(*filters)
        .group_by(Event.type)
        .all()
    )


def get_events_by_hour(*filters):
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
    return (
        db.session.query(
            Bus.plate,
            func.count(Event.id).label("total_events"),
            func.sum(case((Event.type == "Frenado brusco", 1), else_=0)).label("frenado_brusco"),
            func.sum(case((Event.type == "Exceso de velocidad", 1), else_=0)).label("exceso_velocidad"),
            func.sum(case((Event.type == "Curva pronunciada", 1), else_=0)).label("curva_pronunciada"),
            func.sum(case((Event.type == "Conducción agresiva", 1), else_=0)).label("conduccion_agresiva"),
            func.sum(case((Event.type == "Sobrecalentamiento", 1), else_=0)).label("sobrecalentamiento"),
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


def build_group_stats(start_time, end_time, speed_limit):
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


@reports_bp.route("/reports")
@login_required
def reports():
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


@reports_bp.route("/reports/download_csv")
@login_required
def download_csv():
    selected_period, start_time, end_time, _speed_limit = get_report_filter_values()
    selected_bus_id = request.args.get("bus_id", type=int)
    output = io.StringIO()
    writer = csv.writer(output)

    if selected_bus_id:
        bus = Bus.query.get_or_404(selected_bus_id)
        writer.writerow([f"Vehiculo: {bus.plate}"])
        writer.writerow(["Periodo:", selected_period])
        writer.writerow([])
        writer.writerow(["ID", "Tipo", "Valor", "Fecha/Hora", "Latitud", "Longitud", "Descripcion"])
        events = Event.query.filter(
            Event.bus_id == selected_bus_id,
            Event.timestamp.between(start_time, end_time),
        ).all()
        for event in events:
            writer.writerow([event.id, event.type, event.value, event.timestamp, event.latitude, event.longitude, getattr(event, "description", None)])
    else:
        writer.writerow(["Flota completa"])
        writer.writerow(["Periodo:", selected_period])
        writer.writerow([])
        writer.writerow(["ID", "Bus ID", "Tipo", "Valor", "Fecha/Hora", "Latitud", "Longitud", "Descripcion"])
        events = Event.query.filter(Event.timestamp.between(start_time, end_time)).all()
        for event in events:
            writer.writerow([event.id, event.bus_id, event.type, event.value, event.timestamp, event.latitude, event.longitude, getattr(event, "description", None)])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=reportes_{selected_period}.csv"},
    )


@reports_bp.route("/reports/download_tables", methods=["GET", "POST"])
@login_required
def download_tables():
    if request.method == "POST":
        selected_tables = request.form.getlist("tables")
        selected_period = request.form.get("period", "month")
        start_time, end_time = get_time_filter(selected_period)

        output = io.StringIO()
        writer = csv.writer(output)

        for table in selected_tables:
            writer.writerow([f"Tabla: {table.upper()}"])
            writer.writerow([])

            if table == "bus":
                writer.writerow(["ID", "Placa", "Conductor", "Estado"])
                for bus in Bus.query.order_by(Bus.id.asc()).all():
                    writer.writerow([bus.id, bus.plate, bus.driver, bus.status])

            elif table == "event":
                writer.writerow(["ID", "Bus ID", "Tipo", "Valor", "Fecha/Hora", "Latitud", "Longitud", "Descripcion"])
                for event in Event.query.filter(Event.timestamp.between(start_time, end_time)).all():
                    writer.writerow([event.id, event.bus_id, event.type, event.value, event.timestamp, event.latitude, event.longitude, getattr(event, "description", None)])

            elif table == "maintenance":
                writer.writerow(["ID", "Bus ID", "Descripcion", "Fecha", "Estado"])
                for maintenance in Maintenance.query.filter(Maintenance.date.between(start_time, end_time)).all():
                    writer.writerow([maintenance.id, maintenance.bus_id, maintenance.description, maintenance.date, maintenance.status])

            elif table == "location":
                writer.writerow(["ID", "Bus ID", "Latitud", "Longitud", "Velocidad", "Fecha/Hora"])
                for location in Location.query.filter(Location.timestamp.between(start_time, end_time)).all():
                    writer.writerow([location.id, location.bus_id, location.lat, location.lon, location.speed, location.timestamp])

            writer.writerow([])

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=tables_{selected_period}.csv"},
        )

    selected_period = request.args.get("period", "month")
    return render_template("download_tables.html", selected_period=selected_period)
