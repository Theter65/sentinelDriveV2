from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from app.decorators import require_admin
from app.extensions import db
from app.models.event import Event
from app.models.location import Location
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.mqtt.subscriber import MQTT_STATE, request_mqtt_reload, test_mqtt_connection
from app.utils.logging import get_logger
from app.utils.system_settings import get_mqtt_form_defaults, get_runtime_mqtt_settings


logger = get_logger(__name__)

admin_bp = Blueprint("admin", __name__)


def _mqtt_form_state() -> dict:
    defaults = get_mqtt_form_defaults(current_app.config)
    state = defaults.copy()
    if request.method == "POST":
        state.update(
            {
                "mqtt_broker": (request.form.get("mqtt_broker") or "").strip(),
                "mqtt_port": (request.form.get("mqtt_port") or "").strip(),
                "mqtt_username": (request.form.get("mqtt_username") or "").strip(),
                "mqtt_topic_gps": (request.form.get("mqtt_topic_gps") or "").strip(),
                "mqtt_topic_event": (request.form.get("mqtt_topic_event") or "").strip(),
            }
        )
    return state


def _admin_panel_context(mqtt_settings_override: dict | None = None) -> dict:
    total_events = Event.query.count()
    total_locations = Location.query.count()
    return {
        "total_events": total_events,
        "total_locations": total_locations,
        "mqtt_state": MQTT_STATE,
        "mqtt_settings": mqtt_settings_override or get_mqtt_form_defaults(current_app.config),
        "mqtt_runtime": get_runtime_mqtt_settings(current_app.config),
    }


def _render_admin_panel(mqtt_settings_override: dict | None = None, status_code: int = 200):
    return (
        render_template(
            "admin.html",
            **_admin_panel_context(mqtt_settings_override=mqtt_settings_override),
        ),
        status_code,
    )


@admin_bp.route("/admin")
@require_admin
def admin_panel():
    return _render_admin_panel()


@admin_bp.route("/admin/purge_history", methods=["POST"])
@require_admin
def purge_history():
    """Borra TODO el historial de Location y Event (solo admin) con re-autenticacion.

    Seguridad:
    - Requiere rol admin.
    - Requiere re-ingresar la contrasena del usuario admin actual.
    - Accion auditada (usuario, IP, timestamp) via logs.
    """
    username = session.get("user")
    password = request.form.get("password") or ""

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        flash("Contrasena incorrecta. No se realizo el borrado.", "danger")
        logger.warning("AUDIT purge_history denied user=%s ip=%s", username, _client_ip())
        return redirect(url_for("dashboard.dashboard"))

    try:
        # Flask-SQLAlchemy inicia transacciones implicitamente; no usamos session.begin()
        # para evitar "A transaction is already begun on this Session".
        db.session.query(Location).delete(synchronize_session=False)
        db.session.query(Event).delete(synchronize_session=False)
        db.session.commit()
        flash("Historial borrado: ubicaciones (GPS) y eventos eliminados correctamente.", "success")
        logger.warning("AUDIT purge_history success user=%s ip=%s", username, _client_ip())
    except Exception as exc:
        db.session.rollback()
        flash("Error al borrar historial. Revisa logs del servidor.", "danger")
        logger.error("AUDIT purge_history error user=%s ip=%s err=%s", username, _client_ip(), exc, exc_info=True)

    return redirect(url_for("dashboard.dashboard"))


@admin_bp.route("/admin/mqtt", methods=["POST"])
@require_admin
def update_mqtt_settings():
    """Actualiza la configuracion MQTT desde el panel de administracion."""
    form_state = _mqtt_form_state()
    username = session.get("user")
    admin_password = request.form.get("admin_password") or ""
    current_user = User.query.filter_by(username=username).first()
    if not current_user or not current_user.check_password(admin_password):
        flash("Contrasena incorrecta. No se aplicaron cambios en MQTT.", "danger")
        logger.warning("AUDIT mqtt_update denied user=%s ip=%s", username, _client_ip())
        return _render_admin_panel(mqtt_settings_override=form_state, status_code=422)

    broker = (request.form.get("mqtt_broker") or "").strip()
    port_raw = (request.form.get("mqtt_port") or "").strip()
    mqtt_username = (request.form.get("mqtt_username") or "").strip()
    topic_gps = (request.form.get("mqtt_topic_gps") or "").strip()
    topic_event = (request.form.get("mqtt_topic_event") or "").strip()
    mqtt_password = request.form.get("mqtt_password") or ""

    try:
        mqtt_port = int(port_raw)
    except ValueError:
        flash("El puerto MQTT debe ser numerico.", "danger")
        return _render_admin_panel(mqtt_settings_override=form_state, status_code=422)

    if mqtt_port <= 0:
        flash("El puerto MQTT debe ser mayor a cero.", "danger")
        return _render_admin_panel(mqtt_settings_override=form_state, status_code=422)

    effective_password = mqtt_password or SystemSetting.get_value("mqtt_password") or current_app.config.get("MQTT_PASSWORD") or ""
    if not all([broker, mqtt_username, topic_gps, topic_event, effective_password]):
        flash("Completa broker, usuario, topics y password MQTT antes de guardar.", "danger")
        return _render_admin_panel(mqtt_settings_override=form_state, status_code=422)

    mqtt_ok, mqtt_message = test_mqtt_connection(
        broker,
        mqtt_port,
        mqtt_username,
        effective_password,
        topics=[
            (topic_gps, 0),
            (topic_event, 1),
        ],
    )
    if not mqtt_ok:
        flash(f"{mqtt_message} Corrige los datos e intenta nuevamente.", "danger")
        logger.warning("AUDIT mqtt_update validation_failed user=%s ip=%s", username, _client_ip())
        return _render_admin_panel(mqtt_settings_override=form_state, status_code=422)

    try:
        SystemSetting.set_value("mqtt_broker", broker)
        SystemSetting.set_value("mqtt_port", str(mqtt_port))
        SystemSetting.set_value("mqtt_username", mqtt_username)
        SystemSetting.set_value("mqtt_topic_gps", topic_gps)
        SystemSetting.set_value("mqtt_topic_event", topic_event)
        if mqtt_password:
            SystemSetting.set_value("mqtt_password", mqtt_password)

        db.session.commit()
        request_mqtt_reload()
        flash("Configuracion MQTT actualizada. La conexion se reiniciara en unos segundos.", "success")
        logger.warning("AUDIT mqtt_update success user=%s ip=%s", username, _client_ip())
    except Exception as exc:
        db.session.rollback()
        flash("No se pudo actualizar la configuracion MQTT. Revisa los logs.", "danger")
        logger.error("AUDIT mqtt_update error user=%s ip=%s err=%s", username, _client_ip(), exc, exc_info=True)

    return redirect(url_for("admin.admin_panel"))


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"
