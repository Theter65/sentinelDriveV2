"""Endpoints JSON y CSV del modulo de analitica por vehiculo."""

from flask import Blueprint, jsonify, request

from app.decorators import login_required
from app.services.analytics_service import (
    build_analytics_payload,
    generate_analytics_run,
    resolve_filter_values,
)
from app.utils.csv_export import csv_response


analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/analytics/vehicle/<int:bus_id>/generate", methods=["POST"])
@login_required
def generate_vehicle_analytics(bus_id):
    """Genera y persiste una corrida descriptiva para un vehiculo."""

    date_from, date_to, speed_limit = _request_filter_values()
    notes = _request_value("notes")
    try:
        payload = generate_analytics_run(
            bus_id=bus_id,
            date_from=date_from,
            date_to=date_to,
            speed_limit=speed_limit,
            notes=notes,
        )
    except LookupError:
        return jsonify({"error": "Bus no encontrado"}), 404
    return jsonify(payload), 201


@analytics_bp.route("/analytics/vehicle/<int:bus_id>/summary")
@login_required
def vehicle_summary(bus_id):
    """Entrega resumen analitico en JSON."""
    payload, status = _vehicle_payload(bus_id)
    if status != 200:
        return payload, status
    return jsonify(
        {
            "bus": payload["bus"],
            "filters": payload["filters"],
            "summary": payload["summary"],
            "derived": payload["derived"],
            "intervention_summary": payload["intervention_summary"],
        }
    )


@analytics_bp.route("/analytics/vehicle/<int:bus_id>/events-by-type")
@login_required
def vehicle_events_by_type(bus_id):
    """Entrega eventos agrupados por tipo."""
    payload, status = _vehicle_payload(bus_id)
    if status != 200:
        return payload, status
    return jsonify({"filters": payload["filters"], "data": payload["events_by_type"]})


@analytics_bp.route("/analytics/vehicle/<int:bus_id>/events-by-hour")
@login_required
def vehicle_events_by_hour(bus_id):
    """Entrega eventos agrupados por hora."""
    payload, status = _vehicle_payload(bus_id)
    if status != 200:
        return payload, status
    return jsonify({"filters": payload["filters"], "data": payload["events_by_hour"]})


@analytics_bp.route("/analytics/vehicle/<int:bus_id>/speed-histogram")
@login_required
def vehicle_speed_histogram(bus_id):
    """Entrega histograma de velocidades."""
    payload, status = _vehicle_payload(bus_id)
    if status != 200:
        return payload, status
    return jsonify({"filters": payload["filters"], "data": payload["speed_histogram"]})


@analytics_bp.route("/analytics/vehicle/<int:bus_id>/event-magnitudes")
@login_required
def vehicle_event_magnitudes(bus_id):
    """Entrega magnitudes de eventos por tipo."""
    payload, status = _vehicle_payload(bus_id)
    if status != 200:
        return payload, status
    return jsonify({"filters": payload["filters"], "data": payload["event_magnitudes"]})


@analytics_bp.route("/analytics/vehicle/<int:bus_id>/summary.csv")
@login_required
def download_summary_csv(bus_id):
    """Descarga resumen analitico en CSV."""
    payload, status = _vehicle_payload(bus_id)
    if status != 200:
        return payload, status
    summary = payload["summary"]
    rows = [
        ["Campo", "Valor"],
        ["Bus", payload["bus"]["plate"]],
        ["Fecha desde", summary["date_from"]],
        ["Fecha hasta", summary["date_to"]],
        ["Limite de velocidad", payload["filters"]["speed_limit"]],
        ["Total ubicaciones", summary["total_locations"]],
        ["Muestras validas de velocidad", summary["valid_speed_samples"]],
        ["Total eventos", summary["total_events"]],
        ["Velocidad minima", summary["speed_min"]],
        ["Velocidad maxima", summary["speed_max"]],
        ["Velocidad promedio", summary["speed_avg"]],
        ["Mediana velocidad", summary["speed_median"]],
        ["Percentil 85", summary["speed_p85"]],
        ["Percentil 95", summary["speed_p95"]],
        ["Desviacion estandar", summary["speed_stddev"]],
        ["Coeficiente de variacion", summary["speed_cv"]],
        ["Conteo exceso de velocidad", summary["speeding_count"]],
        ["Porcentaje exceso de velocidad", summary["speeding_percentage"]],
        ["Nivel de Intervencion Operativa", payload["intervention_summary"]["global_level"]],
        ["Recomendacion global", payload["intervention_summary"]["global_recommendation"]],
    ]
    return _csv_response(rows, f"analytics_summary_bus_{bus_id}.csv")


@analytics_bp.route("/analytics/vehicle/<int:bus_id>/events-by-type.csv")
@login_required
def download_events_by_type_csv(bus_id):
    """Descarga eventos por tipo en CSV."""
    payload, status = _vehicle_payload(bus_id)
    if status != 200:
        return payload, status
    rows = [["Tipo de evento", "Cantidad", "Porcentaje"]]
    rows.extend(
        [row["event_type"], row["event_count"], row["event_percentage"]]
        for row in payload["events_by_type"]
    )
    return _csv_response(rows, f"analytics_events_by_type_bus_{bus_id}.csv")


@analytics_bp.route("/analytics/vehicle/<int:bus_id>/events-by-hour.csv")
@login_required
def download_events_by_hour_csv(bus_id):
    """Descarga eventos por hora en CSV."""
    payload, status = _vehicle_payload(bus_id)
    if status != 200:
        return payload, status
    rows = [["Hora", "Total eventos"]]
    rows.extend([row["hour"], row["total_events"]] for row in payload["events_by_hour"])
    return _csv_response(rows, f"analytics_events_by_hour_bus_{bus_id}.csv")


@analytics_bp.route("/analytics/vehicle/<int:bus_id>/speed-histogram.csv")
@login_required
def download_speed_histogram_csv(bus_id):
    """Descarga histograma de velocidad en CSV."""
    payload, status = _vehicle_payload(bus_id)
    if status != 200:
        return payload, status
    rows = [["Rango", "Inicio", "Fin", "Frecuencia", "Porcentaje"]]
    rows.extend(
        [row["label"], row["bin_start"], row["bin_end"], row["frequency"], row["percentage"]]
        for row in payload["speed_histogram"]
    )
    return _csv_response(rows, f"analytics_speed_histogram_bus_{bus_id}.csv")


@analytics_bp.route("/analytics/vehicle/<int:bus_id>/event-magnitudes.csv")
@login_required
def download_event_magnitudes_csv(bus_id):
    """Descarga magnitudes en CSV."""
    payload, status = _vehicle_payload(bus_id)
    if status != 200:
        return payload, status
    rows = [["Tipo de evento", "Valor maximo", "Valor promedio", "Cantidad", "Unidad"]]
    rows.extend(
        [row["event_type"], row["max_value"], row["avg_value"], row["count"], row.get("unit", "")]
        for row in payload["event_magnitudes"]
    )
    return _csv_response(rows, f"analytics_event_magnitudes_bus_{bus_id}.csv")


@analytics_bp.route("/analytics/vehicle/<int:bus_id>/intervention-matrix.csv")
@login_required
def download_intervention_matrix_csv(bus_id):
    """Descarga la matriz de intervencion en CSV."""
    payload, status = _vehicle_payload(bus_id)
    if status != 200:
        return payload, status
    rows = [["Indicador", "Valor observado", "Umbral usado", "Nivel", "Recomendacion"]]
    rows.extend(
        [
            row["indicator"],
            row["observed_value"],
            row["threshold_used"],
            row["level"],
            row["recommendation"],
        ]
        for row in payload["intervention_summary"]["matrix"]
    )
    return _csv_response(rows, f"analytics_intervention_matrix_bus_{bus_id}.csv")


@analytics_bp.route("/analytics/vehicle/<int:bus_id>/recommendations.csv")
@login_required
def download_recommendations_csv(bus_id):
    """Descarga recomendaciones descriptivas en CSV."""
    payload, status = _vehicle_payload(bus_id)
    if status != 200:
        return payload, status
    rows = [["#", "Recomendacion"]]
    rows.extend(
        [index, recommendation]
        for index, recommendation in enumerate(
            payload["intervention_summary"]["recommendations"],
            start=1,
        )
    )
    return _csv_response(rows, f"analytics_recommendations_bus_{bus_id}.csv")


def _vehicle_payload(bus_id: int):
    date_from, date_to, speed_limit = _request_filter_values()
    try:
        payload = build_analytics_payload(bus_id, date_from, date_to, speed_limit)
    except LookupError:
        return jsonify({"error": "Bus no encontrado"}), 404
    return payload, 200


def _request_filter_values():
    return resolve_filter_values(_request_data())


def _request_data() -> dict:
    data = {}
    if request.is_json:
        data.update(request.get_json(silent=True) or {})
    data.update(request.args.to_dict())
    data.update(request.form.to_dict())
    return data


def _request_value(key: str):
    return _request_data().get(key)


def _csv_response(rows, filename: str):
    return csv_response(rows, filename)
