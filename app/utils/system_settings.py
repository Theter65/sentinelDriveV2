from app.models.system_setting import SystemSetting
from app.models.user import User


def has_admin_user() -> bool:
    return User.query.filter_by(role="admin").count() > 0


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_runtime_mqtt_settings(config: dict) -> dict:
    stored_password = SystemSetting.get_value("mqtt_password")
    fallback_password = config.get("MQTT_PASSWORD") or ""

    broker = (SystemSetting.get_value("mqtt_broker") or config.get("MQTT_BROKER") or "").strip()
    port = _safe_int(SystemSetting.get_value("mqtt_port"), config.get("MQTT_PORT", 8883))
    username = (SystemSetting.get_value("mqtt_username") or config.get("MQTT_USERNAME") or "").strip()
    password = stored_password or fallback_password
    topic_gps = (SystemSetting.get_value("mqtt_topic_gps") or config.get("MQTT_TOPIC_GPS") or "").strip()
    topic_event = (SystemSetting.get_value("mqtt_topic_event") or config.get("MQTT_TOPIC_EVENT") or "").strip()

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
