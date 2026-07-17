# app/utils/system_settings.py - Configuración MQTT y estado runtime
#
# Centraliza la lógica de lectura/escritura de configuración MQTT
# (broker, puerto, credenciales, tópicos) desde SystemSetting (BD)
# con fallback a variables de entorno. También persiste y consulta
# el estado operativo MQTT (conectado, heartbeat, errores) para
# compartirlo entre procesos web y worker.
# =============================================================================

from datetime import datetime

from app.models.system_setting import SystemSetting
from app.models.user import User
from app.utils.time import ECUADOR_TZ, ecuador_now


DEFAULT_MQTT_PORT = 8883
DEFAULT_MQTT_TOPIC_GPS = "flota/ecuador/buses/+/gps"
DEFAULT_MQTT_TOPIC_EVENT = "flota/ecuador/buses/+/event"
MQTT_STATE_PREFIX = "mqtt_state_"

MQTT_STATUS_LABELS = {
    "no_config": "MQTT no configurado",
    "connecting": "Conectando",
    "online": "En línea",
    "offline": "Offline",
    "error": "Error de conexión MQTT",
}


def has_admin_user() -> bool:
    """Indica si la plataforma ya tiene administrador inicial."""
    return User.query.filter_by(role="admin").count() > 0


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_runtime_mqtt_settings(config: dict) -> dict:
    """Une configuracion MQTT de base de datos y entorno."""
    stored_password = SystemSetting.get_value("mqtt_password")
    fallback_password = config.get("MQTT_PASSWORD") or ""

    broker = (SystemSetting.get_value("mqtt_broker") or config.get("MQTT_BROKER") or "").strip()
    port = _safe_int(SystemSetting.get_value("mqtt_port"), config.get("MQTT_PORT", DEFAULT_MQTT_PORT))
    username = (SystemSetting.get_value("mqtt_username") or config.get("MQTT_USERNAME") or "").strip()
    password = stored_password or fallback_password
    topic_gps = (
        SystemSetting.get_value("mqtt_topic_gps")
        or config.get("MQTT_TOPIC_GPS")
        or DEFAULT_MQTT_TOPIC_GPS
    ).strip()
    topic_event = (
        SystemSetting.get_value("mqtt_topic_event")
        or config.get("MQTT_TOPIC_EVENT")
        or DEFAULT_MQTT_TOPIC_EVENT
    ).strip()

    ready = all([broker, port > 0, username, password, topic_gps, topic_event])

    return {
        "broker": broker,
        "port": port,
        "username": username,
        "password": password,
        "topic_gps": topic_gps,
        "topic_event": topic_event,
        "topics": [
            (topic_gps, 0),
            (topic_event, 1),
        ],
        "ready": ready,
        "password_saved": bool(stored_password),
        "using_env_fallback": bool(not stored_password and fallback_password),
    }


def get_mqtt_form_defaults(config: dict) -> dict:
    """Prepara valores seguros para formularios MQTT."""
    runtime = get_runtime_mqtt_settings(config)
    return {
        "mqtt_broker": runtime["broker"],
        "mqtt_port": runtime["port"],
        "mqtt_username": runtime["username"],
        "mqtt_topic_gps": runtime["topic_gps"],
        "mqtt_topic_event": runtime["topic_event"],
        "mqtt_password_saved": runtime["password_saved"],
        "mqtt_password_available": bool(runtime["password"]),
        "mqtt_using_env_fallback": runtime["using_env_fallback"],
        "mqtt_ready": runtime["ready"],
    }


def update_mqtt_runtime_state(**state) -> None:
    """Persiste estado operativo MQTT para procesos separados (web/worker)."""
    for key, value in state.items():
        setting_key = f"{MQTT_STATE_PREFIX}{key}"
        if value is None:
            SystemSetting.delete_value(setting_key)
        elif isinstance(value, bool):
            SystemSetting.set_value(setting_key, "1" if value else "0")
        elif hasattr(value, "isoformat"):
            SystemSetting.set_value(setting_key, value.isoformat())
        else:
            SystemSetting.set_value(setting_key, str(value))


def get_persisted_mqtt_state(config: dict) -> dict:
    """Lee estado MQTT, priorizando memoria del subscriber sobre DB."""
    runtime = get_runtime_mqtt_settings(config)

    mem_state = _get_in_memory_mqtt_state()

    if mem_state is not None:
        status = mem_state.get("status") or "offline"
        connected = bool(mem_state.get("connected", False))
        heartbeat = mem_state.get("last_heartbeat")
        last_connect = mem_state.get("last_connect")
        last_disconnect = mem_state.get("last_disconnect")
        last_message = mem_state.get("last_message")
        last_error = mem_state.get("last_error")
    else:
        status = SystemSetting.get_value(f"{MQTT_STATE_PREFIX}status")
        connected = _setting_bool(SystemSetting.get_value(f"{MQTT_STATE_PREFIX}connected"), False)
        heartbeat = _parse_datetime_setting(SystemSetting.get_value(f"{MQTT_STATE_PREFIX}last_heartbeat"))
        last_connect = _parse_datetime_setting(SystemSetting.get_value(f"{MQTT_STATE_PREFIX}last_connect"))
        last_disconnect = _parse_datetime_setting(SystemSetting.get_value(f"{MQTT_STATE_PREFIX}last_disconnect"))
        last_message = _parse_datetime_setting(SystemSetting.get_value(f"{MQTT_STATE_PREFIX}last_message"))
        last_error = SystemSetting.get_value(f"{MQTT_STATE_PREFIX}last_error")

    if not runtime["ready"]:
        if status != "no_config":
            status = "no_config"
            connected = False
    elif not status or status == "no_config":
        status = "offline"

    if connected and heartbeat:
        hb = heartbeat
        if hb.tzinfo is None:
            hb = hb.replace(tzinfo=ECUADOR_TZ)
        age_seconds = (ecuador_now() - hb).total_seconds()
        if age_seconds > 120:
            connected = False
            status = "offline"

    if connected:
        status = "online"

    return {
        "connected": connected,
        "configuration_ready": runtime["ready"],
        "status": status,
        "label": MQTT_STATUS_LABELS.get(status, "Offline"),
        "broker": runtime["broker"] or None,
        "topic_gps": runtime["topic_gps"] or None,
        "topic_event": runtime["topic_event"] or None,
        "last_connect": last_connect,
        "last_disconnect": last_disconnect,
        "last_message": last_message,
        "last_heartbeat": heartbeat,
        "last_error": last_error,
    }


def _get_in_memory_mqtt_state():
    """Intenta leer el estado MQTT directamente del subscriber en memoria."""
    try:
        from app.mqtt.subscriber import MQTT_STATE
        if MQTT_STATE.get("status") and MQTT_STATE["status"] != "no_config":
            return dict(MQTT_STATE)
    except (ImportError, RuntimeError):
        pass
    return None


def _setting_bool(value, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_datetime_setting(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ECUADOR_TZ)
    return parsed.astimezone(ECUADOR_TZ)
