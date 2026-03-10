import json
import ssl
import time
from datetime import datetime

import paho.mqtt.client as mqtt

from app.extensions import db
from app.models.bus import Bus
from app.models.event import Event
from app.models.location import Location
from app.mqtt.deduplication import should_process_message
from app.utils.logging import get_logger
from app.utils.time import ECUADOR_TZ


logger = get_logger(__name__)

MQTT_TOPICS = [
    ("flota/ecuador/buses/+/gps", 0),
    ("flota/ecuador/buses/+/event", 1),
]

EVENT_MAPPING = {
    "exceso_velocidad": "Exceso de velocidad",
    "frenado_brusco": "Frenado brusco",
    "curva_peligrosa": "Curva pronunciada",
    "conduccion_agresiva": "Conducción agresiva",
    "sobrecalentamiento": "Sobrecalentamiento",
}


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        logger.info("MQTT: conexion exitosa al broker")
        for topic, qos in MQTT_TOPICS:
            client.subscribe(topic, qos=qos)
            logger.info("MQTT: suscrito a %s (QoS %s)", topic, qos)
    else:
        logger.error("MQTT: fallo de conexion - codigo %s", reason_code)


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
    if reason_code == 0:
        logger.info("MQTT: desconexion limpia")
    else:
        logger.warning("MQTT: desconexion inesperada - codigo %s", reason_code)


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
    return None


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
        latitude=data.get("lat"),
        longitude=data.get("lon"),
        timestamp=timestamp,
    )


def on_message(client, userdata, msg, app):
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
            if not should_process_message(
                bus_id,
                timestamp,
                event_type=event_name,
                value=event_value,
                extra_key=f"{message_kind}|{coords_key}",
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
            logger.info("MQTT: datos procesados - bus %s | tipo: %s", bus_id, message_kind)
        except json.JSONDecodeError:
            logger.error("MQTT: payload JSON invalido")
            db.session.rollback()
        except ValueError as exc:
            logger.error("MQTT: error de validacion: %s", exc)
            db.session.rollback()
        except Exception as exc:
            logger.error("MQTT: error al procesar mensaje: %s", exc, exc_info=True)
            db.session.rollback()
        finally:
            db.session.remove()


def start_mqtt_subscriber(app):
    broker = app.config["MQTT_BROKER"]
    port = app.config["MQTT_PORT"]
    username = app.config["MQTT_USERNAME"]
    password = app.config["MQTT_PASSWORD"]

    client = mqtt.Client(
        protocol=mqtt.MQTTv5,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = lambda c, u, m: on_message(c, u, m, app)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.username_pw_set(username, password)

    logger.info("MQTT: iniciando suscriptor...")
    while True:
        try:
            client.connect(broker, port, keepalive=60)
            client.loop_forever(retry_first_connection=True)
        except Exception as exc:
            logger.error("MQTT: error fatal de conexion: %s. Reintentando en 5s", exc, exc_info=True)
            time.sleep(5)
