"""Suscriptor MQTT: valida conexion, procesa telemetria y persiste datos."""

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
from app.utils.system_settings import get_runtime_mqtt_settings, update_mqtt_runtime_state
from app.utils.time import ECUADOR_TZ, ecuador_now


logger = get_logger(__name__)

MQTT_STATE = {
    "connected": False,
    "configuration_ready": False,
    "status": "no_config",
    "broker": None,
    "topic_gps": None,
    "topic_event": None,
    "last_connect": None,
    "last_disconnect": None,
    "last_message": None,
    "last_heartbeat": None,
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
            "No se pudo comprobar la conexion MQTT con esos datos. Revisalos e intenta nuevamente.",
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
    """Actualiza estado y suscripciones cuando MQTT conecta."""
    if reason_code == 0:
        logger.info("MQTT: conexion exitosa al broker")
        for topic, qos in userdata.get("topics", []):
            client.subscribe(topic, qos=qos)
            logger.info("MQTT: suscrito a %s (QoS %s)", topic, qos)
        app = userdata.get("app") if userdata else None
        now = datetime.now(ECUADOR_TZ)
        if app:
            with app.app_context():
                _set_mqtt_state(
                    connected=True,
                    configuration_ready=True,
                    status="online",
                    last_connect=now,
                    last_heartbeat=now,
                    last_error=None,
                )
                db.session.remove()
        else:
            _update_memory_state(
                connected=True,
                configuration_ready=True,
                status="online",
                last_connect=now,
                last_heartbeat=now,
                last_error=None,
            )
    else:
        logger.error("MQTT: fallo de conexion - codigo %s", reason_code)
        app = userdata.get("app") if userdata else None
        if app:
            with app.app_context():
                _set_mqtt_state(
                    connected=False,
                    status="error",
                    last_error=f"connect_rc={reason_code}",
                )
                db.session.remove()
        else:
            _update_memory_state(connected=False, status="error", last_error=f"connect_rc={reason_code}")


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
    """Registra desconexiones MQTT limpias o inesperadas."""
    status = "offline" if reason_code == 0 else "error"
    last_error = None
    if reason_code == 0:
        logger.info("MQTT: desconexion limpia")
    else:
        logger.warning("MQTT: desconexion inesperada - codigo %s", reason_code)
        last_error = f"disconnect_rc={reason_code}"

    app = userdata.get("app") if userdata else None
    now = datetime.now(ECUADOR_TZ)
    if app:
        with app.app_context():
            _set_mqtt_state(
                connected=False,
                status=status,
                last_disconnect=now,
                last_error=last_error,
            )
            db.session.remove()
    else:
        _update_memory_state(
            connected=False,
            status=status,
            last_disconnect=now,
            last_error=last_error,
        )


def _parse_timestamp(timestamp_value: str) -> datetime | None:
    if not timestamp_value:
        return None
    return datetime.fromisoformat(timestamp_value.replace("Z", "+00:00")).astimezone(ECUADOR_TZ)


def _valid_coordinate(value) -> bool:
    return isinstance(value, (int, float))


def _first_present(data: dict, *keys):
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)
    return None


def _extract_speed(data: dict):
    """Usa `speed` como clave canonica y acepta aliases legacy durante la transicion."""
    return _first_present(data, "speed", "speed_obd", "speed_gps")


def _extract_event_value(event_name: str, data: dict):
    if event_name == "exceso_velocidad":
        return _extract_speed(data)
    if event_name == "frenado_brusco":
        return data.get("accel_x")
    if event_name == "curva_peligrosa":
        return data.get("accel_y")
    if event_name == "conduccion_agresiva":
        return data.get("rpm")
    if event_name == "sobrecalentamiento":
        return _first_present(data, "temperature", "temp")
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
        speed=_extract_speed(data),
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
    """Valida, deduplica y guarda mensajes GPS o eventos MQTT."""
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
            event_value = _extract_event_value(event_name, data) if message_kind == "event" else _extract_speed(data)
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

            _set_mqtt_state(
                commit=False,
                connected=True,
                status="online",
                last_message=datetime.now(ECUADOR_TZ),
                last_heartbeat=datetime.now(ECUADOR_TZ),
                last_error=None,
            )
            db.session.commit()
            logger.info("MQTT: datos procesados - bus %s | tipo: %s", bus_id, message_kind)
        except json.JSONDecodeError:
            logger.error("MQTT: payload JSON invalido")
            db.session.rollback()
            _set_mqtt_state(last_error="json_decode")
        except ValueError as exc:
            logger.error("MQTT: error de validacion: %s", exc)
            db.session.rollback()
            _set_mqtt_state(last_error="validation")
        except Exception as exc:
            logger.error("MQTT: error al procesar mensaje: %s", exc, exc_info=True)
            db.session.rollback()
            _set_mqtt_state(last_error="processing")
        finally:
            db.session.remove()


def request_mqtt_reload():
    """Senala al worker MQTT que debe recargar configuracion."""
    MQTT_RELOAD_EVENT.set()


def _update_memory_state(**state):
    for key, value in state.items():
        if key in MQTT_STATE:
            MQTT_STATE[key] = value


def _set_mqtt_state(commit: bool = True, **state):
    _update_memory_state(**state)
    update_mqtt_runtime_state(**state)
    if commit:
        db.session.commit()


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
    """Mantiene vivo el bucle de conexion MQTT y reintentos."""
    waiting_for_config_logged = False

    logger.info("MQTT: iniciando suscriptor...")
    while True:
        client = None
        try:
            with app.app_context():
                mqtt_config = get_runtime_mqtt_settings(app.config)

                _set_mqtt_state(
                    configuration_ready=mqtt_config["ready"],
                    broker=mqtt_config["broker"] or None,
                    topic_gps=mqtt_config["topic_gps"] or None,
                    topic_event=mqtt_config["topic_event"] or None,
                )

                if not mqtt_config["ready"]:
                    _set_mqtt_state(
                        connected=False,
                        status="no_config",
                        last_error="missing_config",
                    )
                    if not waiting_for_config_logged:
                        logger.warning("MQTT: configuracion incompleta; esperando configuracion desde la interfaz.")
                        waiting_for_config_logged = True
                    db.session.remove()
                    MQTT_RELOAD_EVENT.wait(timeout=5)
                    MQTT_RELOAD_EVENT.clear()
                    continue

                waiting_for_config_logged = False
                logger.info("MQTT: configuracion encontrada, iniciando conexion")
                _set_mqtt_state(
                    connected=False,
                    status="connecting",
                    last_error=None,
                    last_heartbeat=ecuador_now(),
                )
                db.session.remove()

            client = _build_client(app, mqtt_config)
            client.connect(mqtt_config["broker"], mqtt_config["port"], keepalive=60)
            client.loop_start()

            last_heartbeat = 0.0
            while not MQTT_RELOAD_EVENT.wait(timeout=1):
                now_ts = datetime.now(ECUADOR_TZ).timestamp()
                if now_ts - last_heartbeat >= 30:
                    with app.app_context():
                        _set_mqtt_state(last_heartbeat=datetime.now(ECUADOR_TZ))
                        db.session.remove()
                    last_heartbeat = now_ts
                continue

            logger.info("MQTT: recarga solicitada; reiniciando conexion")
        except Exception as exc:
            with app.app_context():
                _set_mqtt_state(
                    connected=False,
                    status="error",
                    last_error="connect_failed",
                    last_disconnect=datetime.now(ECUADOR_TZ),
                )
                db.session.remove()
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
