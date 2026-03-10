import json
import os
import random
import ssl
import time
import logging
from datetime import datetime
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

# ────────────────────────────────────────────────
#  Configuración de logging
# ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("SentinelDrive-Simulator")

# ────────────────────────────────────────────────
#  Carga variables de entorno
# ────────────────────────────────────────────────
load_dotenv()

FLEET_SIZE          = 3
GPS_INTERVAL        = 12      # segundos
EVENT_CHECK_INTERVAL = 1      # segundos
EVENT_PROBABILITY   = 0.02    # ~2% por chequeo (~cada segundo)
EVENT_COOLDOWN      = 5 * 60  # 5 minutos

# Broker (HiveMQ Cloud ejemplo)
BROKER_HOST = os.getenv("MQTT_BROKER", "006b41188f8e4c48ad4936cbef2e695a.s1.eu.hivemq.cloud")
BROKER_PORT = int(os.getenv("MQTT_PORT", "8883"))
USERNAME    = os.getenv("MQTT_USERNAME", "CajaN3gr4")
PASSWORD    = os.getenv("MQTT_PASSWORD", "Proyecto12")

BASE_TOPIC = "flota/ecuador/buses"

# Constantes físicas / umbrales
LAT_BASE = -4.0000
LON_BASE = -79.2000
SPEED_LIMIT        = 80.0
BRAKE_THRESHOLD    = -4.5
CURVE_THRESHOLD    = 4.0
RPM_THRESHOLD      = 4000
ACCEL_AGGRESSIVE   = 3.5
TEMP_THRESHOLD     = 95.0

# ────────────────────────────────────────────────
#  Cliente MQTT
# ────────────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        logger.info("Conectado al broker MQTT ✓")
    else:
        logger.error("Fallo al conectar - reason_code = %s", reason_code)

def on_publish(client, userdata, mid, reason_codes, properties):
    # Opcional: logger.debug("Mensaje publicado (mid=%s)", mid)
    pass

client = mqtt.Client(
    protocol=mqtt.MQTTv5,
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
)

client.on_connect = on_connect
client.on_publish = on_publish

client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
client.username_pw_set(USERNAME, PASSWORD)

# Intentamos conectar con logging
logger.info("Intentando conectar a %s:%s ...", BROKER_HOST, BROKER_PORT)
try:
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()
except Exception as e:
    logger.error("No se pudo conectar al broker → %s", e)
    exit(1)

# ────────────────────────────────────────────────
#  Variables de estado
# ────────────────────────────────────────────────
last_gps_send   = [0.0] * FLEET_SIZE
last_event_time = [0.0] * FLEET_SIZE

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def can_generate_event(bus_index: int) -> bool:
    now_ts = time.time()
    if now_ts - last_event_time[bus_index] < EVENT_COOLDOWN:
        return False
    return random.random() < EVENT_PROBABILITY

def generate_gps():
    return {
        "lat": round(LAT_BASE + random.uniform(-0.01, 0.01), 6),
        "lon": round(LON_BASE + random.uniform(-0.01, 0.01), 6),
        "speed_gps": round(random.uniform(0, 110), 1),
    }

def simulate_obd():
    return {
        "speed": round(random.uniform(0, 110), 1),
        "rpm":   random.randint(800, 5200),
        "temp":  round(random.uniform(70, 105), 1),
    }

def simulate_mpu():
    return {
        "accel_x": round(random.uniform(-6, 5), 2),
        "accel_y": round(random.uniform(-5, 5), 2),
    }

# ────────────────────────────────────────────────
#  Mensaje de bienvenida
# ────────────────────────────────────────────────
print("\n" + "="*45)
print("   SIMULADOR SENTINELDRIVE   |   MQTT IoT")
print(f"   Flota: {FLEET_SIZE} buses")
print(f"   GPS cada {GPS_INTERVAL}s    |   Eventos ~{EVENT_PROBABILITY*100:.1f}%")
print(f"   Cooldown eventos: {EVENT_COOLDOWN//60} min")
print("="*45 + "\n")

# ────────────────────────────────────────────────
#  Bucle principal
# ────────────────────────────────────────────────
while True:
    try:
        current_time = time.time()

        for bus_id in range(1, FLEET_SIZE + 1):
            idx = bus_id - 1

            # ─── GPS periódico ───────────────────────────────
            if current_time - last_gps_send[idx] >= GPS_INTERVAL:
                gps = generate_gps()
                payload = {
                    "bus_id": bus_id,
                    "type": "gps",
                    "timestamp": now_iso(),
                    "lat": gps["lat"],
                    "lon": gps["lon"],
                    "speed_gps": gps["speed_gps"],
                }
                topic = f"{BASE_TOPIC}/{bus_id}/gps"
                client.publish(topic, json.dumps(payload), qos=0)
                logger.info(f"GPS enviado → bus {bus_id:2d}  {gps['lat']:.6f}, {gps['lon']:.6f}  {gps['speed_gps']:5.1f} km/h")
                last_gps_send[idx] = current_time

            # ─── Simulaciones sensores ───────────────────────
            obd = simulate_obd()
            mpu = simulate_mpu()
            gps_event = generate_gps()   # posición para el evento

            event = None

            if obd["speed"] > SPEED_LIMIT and can_generate_event(idx):
                event = {
                    "bus_id": bus_id,
                    "type": "event",
                    "event": "exceso_velocidad",
                    "timestamp": now_iso(),
                    "speed_obd": obd["speed"],
                    "lat": gps_event["lat"],
                    "lon": gps_event["lon"],
                }

            elif mpu["accel_x"] < BRAKE_THRESHOLD and can_generate_event(idx):
                event = {
                    "bus_id": bus_id,
                    "type": "event",
                    "event": "frenado_brusco",
                    "timestamp": now_iso(),
                    "accel_x": mpu["accel_x"],
                    "lat": gps_event["lat"],
                    "lon": gps_event["lon"],
                }

            elif abs(mpu["accel_y"]) > CURVE_THRESHOLD and can_generate_event(idx):
                event = {
                    "bus_id": bus_id,
                    "type": "event",
                    "event": "curva_peligrosa",
                    "timestamp": now_iso(),
                    "accel_y": mpu["accel_y"],
                    "lat": gps_event["lat"],
                    "lon": gps_event["lon"],
                }

            elif obd["rpm"] > RPM_THRESHOLD and mpu["accel_x"] > ACCEL_AGGRESSIVE and can_generate_event(idx):
                event = {
                    "bus_id": bus_id,
                    "type": "event",
                    "event": "conduccion_agresiva",
                    "timestamp": now_iso(),
                    "rpm": obd["rpm"],
                    "accel_x": mpu["accel_x"],
                    "lat": gps_event["lat"],
                    "lon": gps_event["lon"],
                }

            elif obd["temp"] > TEMP_THRESHOLD and can_generate_event(idx):
                event = {
                    "bus_id": bus_id,
                    "type": "event",
                    "event": "sobrecalentamiento",
                    "timestamp": now_iso(),
                    "temperature": obd["temp"],
                    "lat": gps_event["lat"],
                    "lon": gps_event["lon"],
                }

            if event:
                topic = f"{BASE_TOPIC}/{bus_id}/event"
                client.publish(topic, json.dumps(event), qos=1)
                logger.warning(f"EVENTO → bus {bus_id:2d} → {event['event']:<18}  {now_iso()}")
                last_event_time[idx] = time.time()

        time.sleep(EVENT_CHECK_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Detenido por el usuario (Ctrl+C)")
        break
    except Exception as e:
        logger.error("Error en bucle principal: %s", e)
        time.sleep(5)