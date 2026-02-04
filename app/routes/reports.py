# =============================================================================
# app/routes/reports.py - Blueprint de reportes estadísticos (VERSIÓN FINAL 100% CORREGIDA)
# =============================================================================
from flask import Blueprint, render_template, request, Response
from app.decorators import login_required
from app.extensions import db
from app.models.bus import Bus
from app.models.location import Location
from app.models.event import Event
from app.models.maintenance import Maintenance
from app.utils.logging import get_logger
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import func, extract, case, and_, or_
import numpy as np
import csv
import io

logger = get_logger(__name__)

reports_bp = Blueprint("reports", __name__)

# -------------------------------------------------------------------------
# Configuración de períodos
# -------------------------------------------------------------------------
PERIODS = {
    "day": timedelta(days=1),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
    "6months": timedelta(days=180),
    "year": timedelta(days=365),
}

def get_time_filter(period):
    now = datetime.now(ZoneInfo("America/Guayaquil"))
    delta = PERIODS.get(period, PERIODS["month"])
    return now - delta, now

# -------------------------------------------------------------------------
# Histograma de velocidad (bins de 10 km/h)
# -------------------------------------------------------------------------
def get_speed_histogram(filter_condition):
    speeds = db.session.query(Location.speed).filter(filter_condition).all()
    speeds = [s[0] for s in speeds if s[0] is not None and s[0] >= 0]
    if not speeds:
        return [], []
    max_speed = int(max(speeds)) + 10
    bins = list(range(0, max_speed + 1, 10))
    hist, _ = np.histogram(speeds, bins=bins)
    return bins[:-1], hist.tolist()

# -------------------------------------------------------------------------
# REPORTES PRINCIPALES
# -------------------------------------------------------------------------
@reports_bp.route("/reports")
@login_required
def reports():
    selected_period = request.args.get("period", "month")
    selected_bus_id = request.args.get("bus_id", type=int)
    start_time, end_time = get_time_filter(selected_period)
    buses = Bus.query.all()

    # =====================================================================
    # ESTADÍSTICAS GRUPALES
    # =====================================================================
    events_by_type = (
        db.session.query(Event.type, func.count(Event.id))
        .filter(Event.timestamp.between(start_time, end_time))
        .group_by(Event.type)
        .all()
    )
    events_by_hour = (
        db.session.query(
            extract("hour", Event.timestamp).label("hour"),
            func.count(Event.id),
        )
        .filter(Event.timestamp.between(start_time, end_time))
        .group_by("hour")
        .order_by("hour")
        .all()
    )
    group_stats = {
        "total_events": sum(e[1] for e in events_by_type),
        "events_by_type": events_by_type,
        "events_by_hour": events_by_hour,
        "avg_speed": db.session.query(func.avg(Location.speed))
        .filter(Location.timestamp.between(start_time, end_time))
        .scalar() or 0,
        "max_speed": db.session.query(func.max(Location.speed))
        .filter(Location.timestamp.between(start_time, end_time))
        .scalar() or 0,
        "min_speed": db.session.query(func.min(Location.speed))
        .filter(
            Location.timestamp.between(start_time, end_time),
            Location.speed > 0,
        )
        .scalar() or 0,
        "risk_score": 0,
    }
    for event_type, count in events_by_type:
        if event_type == "Frenado brusco":
            group_stats["risk_score"] += 0.6 * count
        elif event_type == "Exceso de velocidad":
            group_stats["risk_score"] += 0.4 * count
    group_stats["risk_score"] = round(group_stats["risk_score"], 2)

    bins, hist = get_speed_histogram(Location.timestamp.between(start_time, end_time))
    group_stats["speed_histogram"] = {"bins": bins, "data": hist}

    # -----------------------------------------------------------------
    # Tabla por bus - Eventos por Tipo
    # -----------------------------------------------------------------
    group_stats["bus_events_table"] = (
        db.session.query(
            Bus.plate,
            func.count(Event.id).label("total_events"),
            func.sum(case((Event.type == "Frenado brusco", 1), else_=0)).label("frenado_brusco"),
            func.sum(case((Event.type == "Exceso de velocidad", 1), else_=0)).label("exceso_velocidad"),
            func.sum(case((Event.type == "Curva pronunciada", 1), else_=0)).label("curva_pronunciada"),
            func.sum(case((Event.type == "Conducción agresiva", 1), else_=0)).label("conduccion_agresiva"),
            func.sum(case((Event.type == "Sobrecalentamiento", 1), else_=0)).label("sobrecalentamiento"),
        )
        .outerjoin(
            Event,
            and_(
                Bus.id == Event.bus_id,
                Event.timestamp.between(start_time, end_time),
            ),
        )
        .group_by(Bus.id)
        .all()
    )

    # -----------------------------------------------------------------
    # Tabla de mantenimientos por conductor (SOLO VISUALIZACIÓN - sin 'type')
    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
# Tabla de mantenimientos por conductor (solo visualización - compatible con SQLite)
# -----------------------------------------------------------------
    group_stats["maintenance_by_driver"] = (
    db.session.query(
        Bus.driver.label("driver"),
        func.count(Maintenance.id).label("total_maintenances"),
        func.max(Maintenance.date).label("ultimo_mantenimiento"),  # Fecha más reciente
        # Estado del mantenimiento más reciente (usando subconsulta correlacionada)
        db.session.query(Maintenance.status)
        .filter(Maintenance.bus_id == Bus.id)
        .order_by(Maintenance.date.desc())
        .limit(1)
        .subquery()
        .c.status.label("estado_reciente")
    )
    .join(Maintenance, Bus.id == Maintenance.bus_id)
    .filter(Maintenance.date.between(start_time, end_time))
    .group_by(Bus.driver)
    .all()
)
    
    
    group_chart_data = {
        "labels": [e[0] for e in events_by_type],
        "data": [e[1] for e in events_by_type],
        "hour_labels": [int(h[0]) for h in events_by_hour],
        "hour_data": [h[1] for h in events_by_hour],
    }

    # =====================================================================
    # ESTADÍSTICAS INDIVIDUALES
    # =====================================================================
    individual_stats = None
    individual_chart_data = None
    if selected_bus_id:
        bus = Bus.query.get_or_404(selected_bus_id)
        ind_events_by_type = (
            db.session.query(Event.type, func.count(Event.id))
            .filter(
                Event.bus_id == selected_bus_id,
                Event.timestamp.between(start_time, end_time),
            )
            .group_by(Event.type)
            .all()
        )
        ind_events_by_hour = (
            db.session.query(
                extract("hour", Event.timestamp).label("hour"),
                func.count(Event.id),
            )
            .filter(
                Event.bus_id == selected_bus_id,
                Event.timestamp.between(start_time, end_time),
            )
            .group_by("hour")
            .order_by("hour")
            .all()
        )
        individual_stats = {
            "bus": bus,
            "total_events": sum(e[1] for e in ind_events_by_type),
            "events_by_type": ind_events_by_type,
            "events_by_hour": ind_events_by_hour,
            "avg_speed": db.session.query(func.avg(Location.speed))
            .filter(
                Location.bus_id == selected_bus_id,
                Location.timestamp.between(start_time, end_time),
            )
            .scalar() or 0,
            "max_speed": db.session.query(func.max(Location.speed))
            .filter(
                Location.bus_id == selected_bus_id,
                Location.timestamp.between(start_time, end_time),
            )
            .scalar() or 0,
            "min_speed": db.session.query(func.min(Location.speed))
            .filter(
                Location.bus_id == selected_bus_id,
                Location.timestamp.between(start_time, end_time),
                Location.speed > 0,
            )
            .scalar() or 0,
            "risk_score": 0,
        }
        for event_type, count in ind_events_by_type:
            if event_type == "Frenado brusco":
                individual_stats["risk_score"] += 0.6 * count
            elif event_type == "Exceso de velocidad":
                individual_stats["risk_score"] += 0.4 * count
        individual_stats["risk_score"] = round(individual_stats["risk_score"], 2)
        bins, hist = get_speed_histogram(
            and_(
                Location.bus_id == selected_bus_id,
                Location.timestamp.between(start_time, end_time),
            )
        )
        individual_stats["speed_histogram"] = {"bins": bins, "data": hist}
        individual_chart_data = {
            "labels": [e[0] for e in ind_events_by_type],
            "data": [e[1] for e in ind_events_by_type],
            "hour_labels": [int(h[0]) for h in ind_events_by_hour],
            "hour_data": [h[1] for h in ind_events_by_hour],
        }

    return render_template(
        "reports.html",
        buses=buses,
        group_stats=group_stats,
        individual_stats=individual_stats,
        group_chart_data=group_chart_data,
        individual_chart_data=individual_chart_data,
        selected_period=selected_period,
        selected_bus_id=selected_bus_id,
    )

# -------------------------------------------------------------------------
# DESCARGA CSV SIMPLE (solo eventos)
# -------------------------------------------------------------------------
@reports_bp.route("/reports/download_csv")
@login_required
def download_csv():
    selected_period = request.args.get("period", "month")
    selected_bus_id = request.args.get("bus_id", type=int)
    start_time, end_time = get_time_filter(selected_period)
    output = io.StringIO()
    writer = csv.writer(output)
    if selected_bus_id:
        bus = Bus.query.get_or_404(selected_bus_id)
        writer.writerow([f"Vehículo: {bus.plate}"])
        writer.writerow(["Periodo:", selected_period])
        writer.writerow([])
        writer.writerow(["ID", "Tipo", "Valor", "Fecha/Hora", "Latitud", "Longitud"])
        events = Event.query.filter(
            Event.bus_id == selected_bus_id,
            Event.timestamp.between(start_time, end_time),
        ).all()
        for e in events:
            writer.writerow([e.id, e.type, e.value, e.timestamp, e.latitude, e.longitude])
    else:
        writer.writerow(["Flota completa"])
        writer.writerow(["Periodo:", selected_period])
        writer.writerow([])
        writer.writerow(["ID", "Bus ID", "Tipo", "Valor", "Fecha/Hora", "Latitud", "Longitud"])
        events = Event.query.filter(Event.timestamp.between(start_time, end_time)).all()
        for e in events:
            writer.writerow([e.id, e.bus_id, e.type, e.value, e.timestamp, e.latitude, e.longitude])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=reportes_{selected_period}.csv"},
    )

# -------------------------------------------------------------------------
# DESCARGA SELECTIVA DE TABLAS (incluye mantenimientos con 'date')
# -------------------------------------------------------------------------
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
                for b in Bus.query.all():
                    writer.writerow([b.id, b.plate, b.driver, b.status])

            elif table == "event":
                writer.writerow(["ID", "Bus ID", "Tipo", "Valor", "Fecha/Hora", "Latitud", "Longitud"])
                for e in Event.query.filter(Event.timestamp.between(start_time, end_time)).all():
                    writer.writerow([e.id, e.bus_id, e.type, e.value, e.timestamp, e.latitude, e.longitude])

            elif table == "maintenance":
                writer.writerow(["ID", "Bus ID", "Descripción", "Fecha", "Estado"])
                for m in Maintenance.query.filter(
                    Maintenance.date.between(start_time, end_time)
                ).all():
                    writer.writerow([m.id, m.bus_id, m.description, m.date, m.status])

            elif table == "location":
                writer.writerow(["ID", "Bus ID", "Latitud", "Longitud", "Velocidad", "Fecha/Hora"])
                for l in Location.query.filter(Location.timestamp.between(start_time, end_time)).all():
                    writer.writerow([l.id, l.bus_id, l.lat, l.lon, l.speed, l.timestamp])

            writer.writerow([])  # Separador

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=tables_{selected_period}.csv"},
        )

    # GET: muestra formulario
    selected_period = request.args.get("period", "month")
    return render_template("download_tables.html", selected_period=selected_period)