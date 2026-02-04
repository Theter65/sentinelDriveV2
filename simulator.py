import random
import time
import json
from datetime import datetime
import ssl
import paho.mqtt.client as mqtt

# ===================== CONFIGURACIÓN GENERAL =====================
FLEET_SIZE = 3

GPS_INTERVAL = 12               # GPS SIEMPRE cada 12 segundos
EVENT_CHECK_INTERVAL = 1        # Loop rápido

EVENT_PROBABILITY = 0.05        # 5% probabilidad de evento
EVENT_COOLDOWN = 5 * 60        # 5 minutos entre eventos por bus

BROKER = "006b41188f8e4c48ad4936cbef2e695a.s1.eu.hivemq.cloud"
PORT = 8883
USERNAME = "CajaN3gr4"
PASSWORD = "Proyecto12"

BASE_TOPIC = "flota/ecuador/buses"

# Coordenadas base (Loja)
LAT_BASE = -4.0000
LON_BASE = -79.2000

# ===================== UMBRALES =====================
SPEED_LIMIT = 80.0
BRAKE_THRESHOLD = -4.5
CURVE_THRESHOLD = 4.0
RPM_THRESHOLD = 4000
ACCEL_AGGRESSIVE = 3.5
TEMP_THRESHOLD = 95.0
# ===================================================

# ===================== MQTT =====================
client = mqtt.Client(
    protocol=mqtt.MQTTv5,
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2
)

client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
client.username_pw_set(USERNAME, PASSWORD)
client.connect(BROKER, PORT, keepalive=60)
client.loop_start()
# =================================================

last_gps_send = [0] * FLEET_SIZE
last_event_time = [0] * FLEET_SIZE

# ===================== UTILIDADES =====================
def now():
    return datetime.now().isoformat(timespec="seconds")

def can_generate_event(bus_index):
    now_ts = time.time()

    if now_ts - last_event_time[bus_index] < EVENT_COOLDOWN:
        return False

    return random.random() < EVENT_PROBABILITY

def generate_gps():
    return {
        "lat": round(LAT_BASE + random.uniform(-0.01, 0.01), 6),
        "lon": round(LON_BASE + random.uniform(-0.01, 0.01), 6),
        "speed_gps": round(random.uniform(0, 110), 1)
    }

def simulate_obd():
    return {
        "speed": round(random.uniform(0, 110), 1),
        "rpm": random.randint(800, 5200),
        "temp": round(random.uniform(70, 105), 1)
    }

def simulate_mpu():
    return {
        "accel_x": round(random.uniform(-6, 5), 2),
        "accel_y": round(random.uniform(-5, 5), 2)
    }
# ===================================================

print("\n=== SIMULADOR SENTINLDRIVE | MQTT IoT ===")
print("• GPS cada 12s (constante)")
print("• Eventos raros (5%)")
print("• Cooldown eventos: 15 min por bus")
print("========================================\n")

# ===================== LOOP PRINCIPAL =====================
while True:
    current_time = time.time()

    for bus_id in range(1, FLEET_SIZE + 1):
        bus_index = bus_id - 1

        # ---------- GPS ----------
        if current_time - last_gps_send[bus_index] >= GPS_INTERVAL:
            gps = generate_gps()

            gps_payload = {
                "bus_id": bus_id,
                "type": "gps",
                "timestamp": now(),
                "lat": gps["lat"],
                "lon": gps["lon"],
                "speed_gps": gps["speed_gps"]
            }

            client.publish(
                f"{BASE_TOPIC}/{bus_id}/gps",
                json.dumps(gps_payload),
                qos=0
            )

            last_gps_send[bus_index] = current_time

        # ---------- SENSORES ----------
        obd = simulate_obd()
        mpu = simulate_mpu()
        gps_event = generate_gps()

        # ---------- EVENTOS ----------
        if obd["speed"] > SPEED_LIMIT and can_generate_event(bus_index):
            event = {
                "bus_id": bus_id,
                "type": "event",
                "event": "exceso_velocidad",
                "timestamp": now(),
                "speed_obd": obd["speed"],
                "lat": gps_event["lat"],
                "lon": gps_event["lon"]
            }
            client.publish(f"{BASE_TOPIC}/{bus_id}/event", json.dumps(event), qos=1)
            last_event_time[bus_index] = time.time()

        elif mpu["accel_x"] < BRAKE_THRESHOLD and can_generate_event(bus_index):
            event = {
                "bus_id": bus_id,
                "type": "event",
                "event": "frenado_brusco",
                "timestamp": now(),
                "accel_x": mpu["accel_x"],
                "lat": gps_event["lat"],
                "lon": gps_event["lon"]
            }
            client.publish(f"{BASE_TOPIC}/{bus_id}/event", json.dumps(event), qos=1)
            last_event_time[bus_index] = time.time()

        elif abs(mpu["accel_y"]) > CURVE_THRESHOLD and can_generate_event(bus_index):
            event = {
                "bus_id": bus_id,
                "type": "event",
                "event": "curva_peligrosa",
                "timestamp": now(),
                "accel_y": mpu["accel_y"],
                "lat": gps_event["lat"],
                "lon": gps_event["lon"]
            }
            client.publish(f"{BASE_TOPIC}/{bus_id}/event", json.dumps(event), qos=1)
            last_event_time[bus_index] = time.time()

        elif obd["rpm"] > RPM_THRESHOLD and mpu["accel_x"] > ACCEL_AGGRESSIVE and can_generate_event(bus_index):
            event = {
                "bus_id": bus_id,
                "type": "event",
                "event": "conduccion_agresiva",
                "timestamp": now(),
                "rpm": obd["rpm"],
                "accel_x": mpu["accel_x"],
                "lat": gps_event["lat"],
                "lon": gps_event["lon"]
            }
            client.publish(f"{BASE_TOPIC}/{bus_id}/event", json.dumps(event), qos=1)
            last_event_time[bus_index] = time.time()

        elif obd["temp"] > TEMP_THRESHOLD and can_generate_event(bus_index):
            event = {
                "bus_id": bus_id,
                "type": "event",
                "event": "sobrecalentamiento",
                "timestamp": now(),
                "temperature": obd["temp"],
                "lat": gps_event["lat"],
                "lon": gps_event["lon"]
            }
            client.publish(f"{BASE_TOPIC}/{bus_id}/event", json.dumps(event), qos=1)
            last_event_time[bus_index] = time.time()

    time.sleep(EVENT_CHECK_INTERVAL)
