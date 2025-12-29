# =============================================================================
# app/mqtt/subscriber.py - Suscriptor MQTT independiente
# =============================================================================
import paho.mqtt.client as mqtt
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from app.extensions import db
from app.models.bus import Bus
from app.models.location import Location
from app.models.event import Event
from app.mqtt.deduplication import should_process_message
from app.utils.logging import get_logger

logger = get_logger(__name__)

MQTT_BROKER = "006b41188f8e4c48ad4936cbef2e695a.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USERNAME = "CajaN3gr4"
MQTT_PASSWORD = "Proyecto12"  # ¡CAMBIAR EN PRODUCCIÓN!

MQTT_TOPICS = [
    ("flota/ecuador/buses/+/position", 0),
    ("flota/ecuador/buses/+/alertas", 1)
]

EVENT_DEDUP_SECONDS = 10

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info("MQTT: Conexión exitosa al broker HiveMQ Cloud")
        for topic, qos in MQTT_TOPICS:
            client.subscribe(topic, qos=qos)
            logger.info(f"MQTT: Suscrito a {topic} (QoS {qos})")
    else:
        logger.error(f"MQTT: Falló conexión - código {rc}")

def on_message(client, userdata, msg, app):  # ← Recibe app
    try:
        with app.app_context():
            topic = msg.topic
            data = json.loads(msg.payload.decode("utf-8"))
            bus_id = int(data.get("bus_id", 0))
            if bus_id == 0:
                logger.warning("MQTT: Mensaje sin bus_id válido")
                return

            bus = Bus.query.get(bus_id)
            if not bus:
                logger.warning(f"MQTT: Bus {bus_id} no registrado")
                return

            ts_str = data.get("timestamp")
            if not ts_str:
                logger.warning("MQTT: Mensaje sin timestamp")
                return

            timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(ZoneInfo("America/Guayaquil"))

            if not should_process_message(bus_id, timestamp):
                return

            location = Location(
                bus_id=bus_id,
                lat=data.get("lat"),
                lon=data.get("lon"),
                speed=data.get("speed"),
                timestamp=timestamp
            )
            db.session.add(location)

            if "alertas" in topic:
                for ev in data.get("events", []):
                    value = {
                        "Exceso de velocidad": data.get("speed"),
                        "Frenado brusco": data.get("accel"),
                        "Curva pronunciada": data.get("gyro"),
                    }.get(ev)

                    event = Event(
                        bus_id=bus_id,
                        type=ev,
                        value=value,
                        timestamp=timestamp
                    )
                    db.session.add(event)

            db.session.commit()
            logger.info(f"MQTT: Datos procesados correctamente - bus {bus_id}")

    except Exception as e:
        logger.error(f"MQTT: Error al procesar mensaje: {e}")
        if db.session.is_active:
            db.session.rollback()

def start_mqtt_subscriber(app):  # ← Recibe app como parámetro
    client = mqtt.Client(protocol=mqtt.MQTTv5, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = lambda c, u, m: on_message(c, u, m, app)  # Pasa app al callback
    client.tls_set()
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    logger.info("MQTT: Iniciando suscriptor...")
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_forever()