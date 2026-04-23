import json
import ssl
import threading
from datetime import datetime

import paho.mqtt.client as mqtt

from app.extensions import db
from app.models.bus import Bus
from app.models.event import Event
from app.models.location import Location
from app.mqtt.deduplication import should_process_message
from app.utils.logging import get_logger
from app.utils.system_settings import get_runtime_mqtt_settings
from app.utils.time import ECUADOR_TZ


logger = get_logger(__name__)

MQTT_STATE = {
    "connected": False,
    "configuration_ready": False,
    "broker": None,
    "topic_gps": None,
    "topic_event": None,
    "last_connect": None,
    "last_disconnect": None,
    "last_message": None,
    "last_error": None,
}

MQTT_RELOAD_EVENT = threading.Event()

EVENT_MAPPING = {
    "exceso_velocidad": "Exceso de velocidad",
    "frenado_brusco": "Frenado brusco",
    "curva_peligrosa": "Curva pronunciada",
    "conduccion_agresiva": "Conducción agresiva",
    "sobrecalentamiento": "Sobrecalentamiento",
    # Evento extendido para sensores no estandarizados (presion de llantas, etc.).
    "otros": "Otros",
    "otro": "Otros",
}

MQTT_CONNECT_ERROR_MESSAGES = {
    1: "El servidor no acepto la version del protocolo usada para conectar.",
    2: "El servidor rechazo el identificador de esta conexion.",
    3: "El servicio MQTT no esta disponible en este momento.",
    4: "El usuario o la clave del servidor no son correctos.",
    5: "El servidor rechazo la conexion con estos permisos.",
    128: "El servidor rechazo la conexion de forma general.",
    129: "La conexion fue rechazada por un formato invalido.",
    130: "El identificador de cliente no es valido para el servidor.",
    131: "La version del protocolo no es compatible con el servidor.",
    132: "El servidor no admite el tipo de conexion solicitado.",
    133: "El identificador de cliente no fue aceptado por el servidor.",
    134: "El usuario o la clave del servidor no son correctos.",
    135: "El servidor rechazo el acceso con esos permisos.",
    136: "El servicio MQTT no esta disponible en este momento.",
    137: "El servidor esta ocupado. Intenta de nuevo en unos segundos.",
    138: "El servidor ha cerrado temporalmente la conexion.",
    139: "La conexion fue rechazada por restricciones del servidor.",
    140: "La direccion o el puerto configurados no fueron aceptados.",
    149: "La conexion excedio el tiempo permitido por el servidor.",
}


def _reason_code_value(reason_code) -> int | None:
    if hasattr(reason_code, "value"):
        try:
            return int(reason_code.value)
        except (TypeError, ValueError):
            return None
    try:
        return int(reason_code)
    except (TypeError, ValueError):
        return None


def _mqtt_connect_error_message(reason_code) -> str:
    code = _reason_code_value(reason_code)
    if code == 0:
        return "Conexion establecida correctamente."
    if code in MQTT_CONNECT_ERROR_MESSAGES:
        return MQTT_CONNECT_ERROR_MESSAGES[code]
    if code is None:
        return "No se pudo interpretar la respuesta del servidor MQTT."
    return f"No se pudo establecer la conexion con el servidor MQTT (codigo {code})."


def test_mqtt_connection(
    broker: str,
    port: int,
    username: str,
    password: str,
    topics: list[tuple[str, int]] | None = None,
    timeout: int = 6,
) -> tuple[bool, str]:
    """Valida credenciales MQTT antes de persistir cambios en la interfaz."""
    result = {
        "ok": False,
        "message": "No se pudo completar la comprobacion de la conexion MQTT.",
    }
    handshake_done = threading.Event()

    client = mqtt.Client(
        protocol=mqtt.MQTTv5,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )

    def _on_connect(local_client, userdata, flags, reason_code, properties=None):
        if _reason_code_value(reason_code) == 0:
            try:
                for topic, qos in topics or []:
                    if topic:
                        local_client.subscribe(topic, qos=qos)
                result["ok"] = True
                result["message"] = "Conexion establecida correctamente con el servidor MQTT."
            except Exception:
                result["message"] = "Se pudo conectar al servidor, pero hubo un problema al validar los canales configurados."
        else:
            result["message"] = _mqtt_connect_error_message(reason_code)
        handshake_done.set()

    def _on_disconnect(local_client, userdata, disconnect_flags, reason_code, properties=None):
        if not handshake_done.is_set():
            result["message"] = _mqtt_connect_error_message(reason_code)
            handshake_done.set()

    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.username_pw_set(username, password)

    try:
        client.connect(broker, port, keepalive=60)
        client.loop_start()

        if not handshake_done.wait(timeout=timeout):
            return (
                False,
                "No se pudo establecer la conexion con el servidor MQTT. Revisa la direccion, el puerto y tus credenciales.",
            )
        return result["ok"], result["message"]
    except ssl.SSLError:
        return (
            False,
            "La conexion segura con el servidor MQTT fallo. Verifica que el puerto y la configuracion del servidor sean correctos.",
        )
    except OSError:
        return (
            False,
            "No se pudo llegar al servidor MQTT. Revisa la direccion, el puerto o tu conexion de red.",
        )
    except Exception as exc:
        logger.warning("MQTT: fallo durante la comprobacion manual de conexion: %s", exc, exc_info=True)
        return (
            False,
            "No se pudo comprobar la conexion MQTT con esos datos. Revísalos e intenta nuevamente.",
        )
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        try:
            client.loop_stop()
        except Exception:
            pass


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        logger.info("MQTT: conexion exitosa al broker")
        MQTT_STATE["connected"] = True
        MQTT_STATE["last_connect"] = datetime.now(ECUADOR_TZ)
        MQTT_STATE["last_error"] = None
        for topic, qos in userdata.get("topics", []):
            client.subscribe(topic, qos=qos)
            logger.info("MQTT: suscrito a %s (QoS %s)", topic, qos)
    else:
        logger.error("MQTT: fallo de conexion - codigo %s", reason_code)
        MQTT_STATE["connected"] = False
        MQTT_STATE["last_error"] = f"connect_rc={reason_code}"


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
    if reason_code == 0:
        logger.info("MQTT: desconexion limpia")
    else:
        logger.warning("MQTT: desconexion inesperada - codigo %s", reason_code)
        MQTT_STATE["last_error"] = f"disconnect_rc={reason_code}"
    MQTT_STATE["connected"] = False
    MQTT_STATE["last_disconnect"] = datetime.now(ECUADOR_TZ)


def _parse_timestamp(timestamp_value: str) -> datetime | None:
    if not timestamp_value:
        return None
    return datetime.fromisoformat(timestamp_value.replace("Z", "+00:00")).astimezone(ECUADOR_TZ)


def _valid_coordinate(value) -> bool:
    return isinstance(value, (int, float))


def _extract_event_value(event_name: str, data: dict):
    if event_name == "exceso_velocidad":
        return data.get("speed_obd", data.get("speed_gps"))
    if event_name == "frenado_brusco":
        return data.get("accel_x")
    if event_name == "curva_peligrosa":
        return data.get("accel_y")
    if event_name == "conduccion_agresiva":
        return data.get("rpm")
    if event_name == "sobrecalentamiento":
        return data.get("temperature")
    if event_name in ("otros", "otro"):
        raw = data.get("value")
        if raw is None:
            return None
        if isinstance(raw, (int, float)):
            return raw
        if isinstance(raw, str):
            try:
                return float(raw)
            except ValueError:
                return None
    return None


def _sanitize_description(raw_value) -> str | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str):
        raw_value = str(raw_value)
    desc = raw_value.strip()
    if not desc:
        return None
    # Evita payloads enormes desde MQTT.
    if len(desc) > 300:
        desc = desc[:300]
    return desc


def _build_location(bus_id: int, data: dict, timestamp: datetime) -> Location | None:
    lat = data.get("lat")
    lon = data.get("lon")
    if not (_valid_coordinate(lat) and _valid_coordinate(lon)):
        logger.warning("MQTT: GPS invalido para bus %s", bus_id)
        return None
    return Location(
        bus_id=bus_id,
        lat=lat,
        lon=lon,
        speed=data.get("speed_gps", data.get("speed")),
        timestamp=timestamp,
    )


def _build_event(bus_id: int, data: dict, timestamp: datetime) -> Event | None:
    event_name = data.get("event")
    if event_name not in EVENT_MAPPING:
        logger.warning("MQTT: evento desconocido: %s", event_name)
        return None
    return Event(
        bus_id=bus_id,
        type=EVENT_MAPPING[event_name],
        value=_extract_event_value(event_name, data),
        description=_sanitize_description(data.get("description")),
        latitude=data.get("lat"),
        longitude=data.get("lon"),
        timestamp=timestamp,
    )


def on_message(client, userdata, msg):
    app = userdata["app"]
    with app.app_context():
        try:
            topic = msg.topic
            data = json.loads(msg.payload.decode("utf-8"))
            bus_id = int(data.get("bus_id", 0))
            if bus_id <= 0:
                logger.warning("MQTT: mensaje sin bus_id valido")
                return

            bus = db.session.get(Bus, bus_id)
            if not bus:
                logger.warning("MQTT: bus %s no registrado", bus_id)
                return

            timestamp = _parse_timestamp(data.get("timestamp"))
            if not timestamp:
                logger.warning("MQTT: mensaje sin timestamp valido")
                return

            message_kind = "gps" if "gps" in topic else "event"
            event_name = data.get("event") if message_kind == "event" else "gps"
            event_value = _extract_event_value(event_name, data) if message_kind == "event" else data.get("speed_gps", data.get("speed"))
            coords_key = f"{data.get('lat')}|{data.get('lon')}"
            desc_key = ""
            if message_kind == "event" and event_name in ("otros", "otro"):
                desc_key = f"|{_sanitize_description(data.get('description')) or ''}"
            if not should_process_message(
                bus_id,
                timestamp,
                event_type=event_name,
                value=event_value,
                extra_key=f"{message_kind}|{coords_key}{desc_key}",
            ):
                return

            if message_kind == "gps":
                location = _build_location(bus_id, data, timestamp)
                if location is None:
                    return
                db.session.add(location)
            else:
                event = _build_event(bus_id, data, timestamp)
                if event is None:
                    return
                db.session.add(event)

            db.session.commit()
            MQTT_STATE["last_message"] = datetime.now(ECUADOR_TZ)
            logger.info("MQTT: datos procesados - bus %s | tipo: %s", bus_id, message_kind)
        except json.JSONDecodeError:
            logger.error("MQTT: payload JSON invalido")
            MQTT_STATE["last_error"] = "json_decode"
            db.session.rollback()
        except ValueError as exc:
            logger.error("MQTT: error de validacion: %s", exc)
            MQTT_STATE["last_error"] = "validation"
            db.session.rollback()
        except Exception as exc:
            logger.error("MQTT: error al procesar mensaje: %s", exc, exc_info=True)
            MQTT_STATE["last_error"] = "processing"
            db.session.rollback()
        finally:
            db.session.remove()


def request_mqtt_reload():
    MQTT_RELOAD_EVENT.set()


def _build_client(app, mqtt_config: dict):
    client = mqtt.Client(
        protocol=mqtt.MQTTv5,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    client.user_data_set(
        {
            "app": app,
            "topics": mqtt_config["topics"],
        }
    )
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.username_pw_set(mqtt_config["username"], mqtt_config["password"])
    return client


def start_mqtt_subscriber(app):
    waiting_for_config_logged = False

    logger.info("MQTT: iniciando suscriptor...")
    while True:
        client = None
        try:
            with app.app_context():
                mqtt_config = get_runtime_mqtt_settings(app.config)

            MQTT_STATE["configuration_ready"] = mqtt_config["ready"]
            MQTT_STATE["broker"] = mqtt_config["broker"] or None
            MQTT_STATE["topic_gps"] = mqtt_config["topic_gps"] or None
            MQTT_STATE["topic_event"] = mqtt_config["topic_event"] or None

            if not mqtt_config["ready"]:
                MQTT_STATE["connected"] = False
                MQTT_STATE["last_error"] = "missing_config"
                if not waiting_for_config_logged:
                    logger.warning("MQTT: configuracion incompleta. Se esperaran credenciales desde la interfaz.")
                    waiting_for_config_logged = True
                MQTT_RELOAD_EVENT.wait(timeout=5)
                MQTT_RELOAD_EVENT.clear()
                continue

            waiting_for_config_logged = False
            client = _build_client(app, mqtt_config)
            client.connect(mqtt_config["broker"], mqtt_config["port"], keepalive=60)
            client.loop_start()

            while not MQTT_RELOAD_EVENT.wait(timeout=1):
                continue

            logger.info("MQTT: recarga solicitada; reiniciando conexion")
        except Exception as exc:
            MQTT_STATE["connected"] = False
            MQTT_STATE["last_error"] = "connect_failed"
            logger.error("MQTT: error fatal de conexion: %s. Reintentando en 5s", exc, exc_info=True)
            MQTT_RELOAD_EVENT.wait(timeout=5)
        finally:
            MQTT_RELOAD_EVENT.clear()
            if client is not None:
                try:
                    client.disconnect()
                except Exception:
                    pass
                try:
                    client.loop_stop()
                except Exception:
                    pass
