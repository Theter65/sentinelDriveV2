"""Simulador local de datos MQTT para pruebas manuales fuera del repositorio remoto."""

import json
import os
import random
import ssl
import time
import logging
from datetime import datetime
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

# Configuracion de logging para ver publicaciones y errores en consola.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("SentinelDrive-Simulator")

# Carga variables de entorno locales para no dejar credenciales en el codigo.
load_dotenv()

FLEET_SIZE          = 3
GPS_INTERVAL        = 12      # segundos
EVENT_CHECK_INTERVAL = 1      # segundos
EVENT_MIN_INTERVAL  = 5 * 60  # 5 minutos
EVENT_MAX_INTERVAL  = 10 * 60 # 10 minutos

# Broker MQTT del simulador. Se toma solo de variables de entorno/.env local.
BROKER_HOST = os.getenv("MQTT_BROKER", "").strip()
try:
    BROKER_PORT = int(os.getenv("MQTT_PORT", "8883"))
except ValueError:
    BROKER_PORT = 0
USERNAME    = os.getenv("MQTT_USERNAME", "").strip()
PASSWORD    = os.getenv("MQTT_PASSWORD", "")

BASE_TOPIC = "flota/ecuador/buses"

# Constantes fisicas y umbrales usados para generar eventos de prueba.
LAT_BASE = -4.0000
LON_BASE = -79.2000
SPEED_LIMIT        = 80.0
BRAKE_THRESHOLD    = -4.5
CURVE_THRESHOLD    = 4.0
RPM_THRESHOLD      = 4000
ACCEL_AGGRESSIVE   = 3.5
TEMP_THRESHOLD     = 95.0
SCHEDULED_EVENTS = (
    "exceso_velocidad",
    "frenado_brusco",
    "curva_peligrosa",
    "conduccion_agresiva",
    "sobrecalentamiento",
    "otros",
)

# Sensores opcionales para eventos extendidos ("otros").
# Estos eventos representan alertas provenientes de hardware no presente en todos los vehiculos.
OTHER_SENSORS = [
    {"description": "Presion de llantas (psi)", "min": 26.0, "max": 42.0, "decimals": 1},
    {"description": "Voltaje de bateria (V)", "min": 11.2, "max": 14.6, "decimals": 2},
    {"description": "Presion de aceite (kPa)", "min": 150.0, "max": 500.0, "decimals": 0},
    {"description": "Nivel de combustible (%)", "min": 0.0, "max": 100.0, "decimals": 0},
]

# Cliente MQTT que publica las muestras simuladas.
def on_connect(client, userdata, flags, reason_code, properties):
    """Registra el resultado de la conexion al broker."""
    if reason_code == 0:
        logger.info("Conectado al broker MQTT correctamente")
    else:
        logger.error("Fallo al conectar - reason_code = %s", reason_code)

def on_publish(client, userdata, mid, reason_codes, properties):
    """Punto de extension para registrar publicaciones si se activa debug."""
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
if not all([BROKER_HOST, BROKER_PORT, USERNAME, PASSWORD]):
    logger.error("Configura MQTT_BROKER, MQTT_PORT, MQTT_USERNAME y MQTT_PASSWORD para usar el simulador.")
    exit(1)

logger.info("Intentando conectar a %s:%s ...", BROKER_HOST, BROKER_PORT)
try:
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()
except Exception as e:
    logger.error("No se pudo conectar al broker -> %s", e)
    exit(1)

# Variables de estado para espaciar publicaciones por bus.
last_gps_send   = [0.0] * FLEET_SIZE
next_event_time = [0.0] * FLEET_SIZE

def now_iso():
    """Devuelve la marca temporal local en formato ISO simple."""
    return datetime.now().isoformat(timespec="seconds")

def schedule_next_event(bus_index: int, from_time: float | None = None) -> None:
    """Programa el siguiente evento simulado para un bus."""
    base_time = from_time if from_time is not None else time.time()
    next_event_time[bus_index] = base_time + random.uniform(EVENT_MIN_INTERVAL, EVENT_MAX_INTERVAL)

def choose_scheduled_event() -> str:
    """Elige aleatoriamente el tipo de evento que se publicara."""
    return random.choice(SCHEDULED_EVENTS)

def simulate_bus_sample(bus_id: int, forced_event: str | None = None) -> dict:
    """Genera una sola muestra coherente de ubicacion, velocidad y sensores.

    La velocidad normal se mantiene bajo el limite. Si la muestra fuerza exceso
    de velocidad, el mismo dato se publica como velocidad canonica y como evento.
    """

    bus_offset = (bus_id - 1) * 0.002
    speed = round(random.uniform(18, SPEED_LIMIT - 2), 1)
    rpm = random.randint(850, 3600)
    temp = round(random.uniform(72, TEMP_THRESHOLD - 4), 1)
    accel_x = round(random.uniform(-2.2, 2.4), 2)
    accel_y = round(random.uniform(-2.2, 2.4), 2)

    if forced_event == "exceso_velocidad":
        speed = round(random.uniform(SPEED_LIMIT + 5, 110), 1)
        rpm = random.randint(1800, 4200)
    elif forced_event == "frenado_brusco":
        accel_x = round(random.uniform(-6.5, BRAKE_THRESHOLD - 0.1), 2)
    elif forced_event == "curva_peligrosa":
        direction = random.choice([-1, 1])
        accel_y = round(direction * random.uniform(CURVE_THRESHOLD + 0.2, 5.8), 2)
    elif forced_event == "conduccion_agresiva":
        rpm = random.randint(RPM_THRESHOLD + 100, 5200)
        accel_x = round(random.uniform(ACCEL_AGGRESSIVE + 0.2, 5.0), 2)
    elif forced_event == "sobrecalentamiento":
        temp = round(random.uniform(TEMP_THRESHOLD + 0.5, 106), 1)

    return {
        "lat": round(LAT_BASE + bus_offset + random.uniform(-0.01, 0.01), 6),
        "lon": round(LON_BASE + bus_offset + random.uniform(-0.01, 0.01), 6),
        "speed": speed,
        "rpm": rpm,
        "temp": temp,
        "accel_x": accel_x,
        "accel_y": accel_y,
    }

def build_gps_payload(bus_id: int, timestamp: str, sample: dict) -> dict:
    """Arma el JSON MQTT de ubicacion GPS."""
    return {
        "bus_id": bus_id,
        "type": "gps",
        "timestamp": timestamp,
        "lat": sample["lat"],
        "lon": sample["lon"],
        "speed": sample["speed"],
    }

def build_event_payload(bus_id: int, timestamp: str, sample: dict, scheduled_event: str | None) -> dict | None:
    """Arma el JSON MQTT de evento segun el tipo programado."""
    if sample["speed"] > SPEED_LIMIT:
        return {
            "bus_id": bus_id,
            "type": "event",
            "event": "exceso_velocidad",
            "timestamp": timestamp,
            "speed": sample["speed"],
            "lat": sample["lat"],
            "lon": sample["lon"],
        }

    if scheduled_event == "frenado_brusco":
        return {
            "bus_id": bus_id,
            "type": "event",
            "event": "frenado_brusco",
            "timestamp": timestamp,
            "accel_x": sample["accel_x"],
            "lat": sample["lat"],
            "lon": sample["lon"],
        }

    if scheduled_event == "curva_peligrosa":
        return {
            "bus_id": bus_id,
            "type": "event",
            "event": "curva_peligrosa",
            "timestamp": timestamp,
            "accel_y": sample["accel_y"],
            "lat": sample["lat"],
            "lon": sample["lon"],
        }

    if scheduled_event == "conduccion_agresiva":
        return {
            "bus_id": bus_id,
            "type": "event",
            "event": "conduccion_agresiva",
            "timestamp": timestamp,
            "rpm": sample["rpm"],
            "accel_x": sample["accel_x"],
            "lat": sample["lat"],
            "lon": sample["lon"],
        }

    if scheduled_event == "sobrecalentamiento":
        return {
            "bus_id": bus_id,
            "type": "event",
            "event": "sobrecalentamiento",
            "timestamp": timestamp,
            "temperature": sample["temp"],
            "lat": sample["lat"],
            "lon": sample["lon"],
        }

    if scheduled_event == "otros":
        description, value = generate_other_sensor_event()
        return {
            "bus_id": bus_id,
            "type": "event",
            "event": "otros",
            "timestamp": timestamp,
            "description": description,
            "value": value,
            "lat": sample["lat"],
            "lon": sample["lon"],
        }

    return None

def generate_other_sensor_event():
    """Genera un evento generico de sensor auxiliar."""
    sensor = random.choice(OTHER_SENSORS)
    value = round(random.uniform(sensor["min"], sensor["max"]), int(sensor["decimals"]))
    return sensor["description"], value

boot_time = time.time()
for bus_index in range(FLEET_SIZE):
    schedule_next_event(bus_index, boot_time)

# Mensaje de bienvenida para confirmar parametros de simulacion.
print("\n" + "="*45)
print("   SIMULADOR SENTINELDRIVE   |   MQTT IoT")
print(f"   Flota: {FLEET_SIZE} buses")
print(f"   GPS cada {GPS_INTERVAL}s    |   Eventos cada 5-10 min por bus")
print(f"   Limite velocidad: {SPEED_LIMIT:.0f} km/h")
print("="*45 + "\n")

# Bucle principal de publicacion MQTT.
while True:
    try:
        current_time = time.time()

        for bus_id in range(1, FLEET_SIZE + 1):
            idx = bus_id - 1

            # Muestra unificada periodica: una lectura GPS y, si aplica, un evento.
            if current_time - last_gps_send[idx] >= GPS_INTERVAL:
                scheduled_event = None
                if current_time >= next_event_time[idx]:
                    scheduled_event = choose_scheduled_event()

                timestamp = now_iso()
                sample = simulate_bus_sample(bus_id, scheduled_event)
                payload = build_gps_payload(bus_id, timestamp, sample)
                topic = f"{BASE_TOPIC}/{bus_id}/gps"
                client.publish(topic, json.dumps(payload), qos=0)
                logger.info(
                    "GPS enviado -> bus %2d  %.6f, %.6f  %5.1f km/h",
                    bus_id,
                    sample["lat"],
                    sample["lon"],
                    sample["speed"],
                )
                last_gps_send[idx] = current_time

                event = build_event_payload(bus_id, timestamp, sample, scheduled_event)
                if event:
                    topic = f"{BASE_TOPIC}/{bus_id}/event"
                    client.publish(topic, json.dumps(event), qos=1)
                    logger.warning(
                        "EVENTO -> bus %2d -> %-18s  %s  %.6f, %.6f  %5.1f km/h",
                        bus_id,
                        event["event"],
                        timestamp,
                        sample["lat"],
                        sample["lon"],
                        sample["speed"],
                    )

                if scheduled_event:
                    schedule_next_event(idx, current_time)

        time.sleep(EVENT_CHECK_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Detenido por el usuario (Ctrl+C)")
        break
    except Exception as e:
        logger.error("Error en bucle principal: %s", e)
        time.sleep(5)
