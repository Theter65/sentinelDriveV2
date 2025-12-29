import random
import time
import json
from datetime import datetime
import paho.mqtt.client as mqtt
import ssl

# ===================== CONFIGURACIÓN =====================
FLEET_SIZE = 3
POSITION_INTERVAL = 12          # segundos - envío constante de posición (10-15s es realista)
EVENT_CHECK_INTERVAL = 4        # segundos - chequeo frecuente de eventos de riesgo

BROKER = "006b41188f8e4c48ad4936cbef2e695a.s1.eu.hivemq.cloud"
PORT = 8883
USERNAME = "CajaN3gr4"
PASSWORD = "Proyecto12"  

BASE_TOPIC = "flota/ecuador/buses"

# Umbrales realistas (basados en literatura de seguridad vial y normativa)
CRITICAL_SPEED_THRESHOLD = 80.0       # km/h
CRITICAL_BRAKE_THRESHOLD = -4.5       # m/s² (~0.46g)
CRITICAL_TURN_THRESHOLD  = 55.0       # °/s

LAT_BASE, LON_BASE = -4.0000, -79.2000  # referencia Loja
# ==========================================================

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("✓ Conectado exitosamente al broker MQTT")
    else:
        print(f"✗ Falló la conexión → código: {rc}")

def on_publish(client, userdata, mid, reason_code=None, properties=None):
    print(f"  → Publicado (mid: {mid})")

client = mqtt.Client(protocol=mqtt.MQTTv5, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_publish = on_publish

client.tls_set(ca_certs=None, cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)
client.username_pw_set(USERNAME, PASSWORD)

print(f"Conectando a {BROKER}:{PORT}...")
client.connect(BROKER, PORT, keepalive=60)
client.loop_start()
time.sleep(2.5)

# Tiempos de último envío de posición por bus
last_position_send = [time.time() - random.uniform(0, 10) for _ in range(FLEET_SIZE)]

def generate_position_update(bus_id):
    """Genera solo la actualización mínima de posición (muy liviana)"""
    lat = LAT_BASE + random.uniform(-0.05, 0.05)   # deriva más amplia para simular movimiento real
    lon = LON_BASE + random.uniform(-0.05, 0.05)
    speed = random.uniform(0, 110)                 # velocidad actual para contexto

    return {
        "bus_id": bus_id,
        "timestamp": datetime.now().isoformat(),
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "speed": round(speed, 1)                   # solo 1 decimal para ahorrar bytes
    }

def simulate_full_telemetry(bus_id):
    """Genera paquete completo (solo se usa cuando hay evento crítico)"""
    speed = random.uniform(0, 110)
    accel = random.uniform(-7.0, 4.0)
    gyro = random.uniform(-120, 120)
    temp = random.uniform(60, 98)

    lat = LAT_BASE + random.uniform(-0.05, 0.05)
    lon = LON_BASE + random.uniform(-0.05, 0.05)

    data = {
        "bus_id": bus_id,
        "timestamp": datetime.now().isoformat(),
        "speed": round(speed, 2),
        "accel": round(accel, 2),
        "gyro": round(gyro, 2),
        "temperature": round(temp, 2),
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "events": []
    }

    if speed > CRITICAL_SPEED_THRESHOLD:
        data["events"].append("Exceso de velocidad")
    if accel < CRITICAL_BRAKE_THRESHOLD:
        data["events"].append("Frenado brusco")
    if abs(gyro) > CRITICAL_TURN_THRESHOLD:
        data["events"].append("Curva pronunciada")

    return data

def run_simulator():
    print("=== Simulador Flota Vehicular - Versión Optimizada 2025 ===")
    print("Política:")
    print("  • Posición (lat/lon) → cada ~12 segundos (obligatorio por normativa)")
    print("  • Telemetría completa + eventos → SOLO cuando existe riesgo")
    print(f"• Buses: {FLEET_SIZE}")
    print(f"• Broker: {BROKER}")
    print("===================================================\n")

    while True:
        current_time = time.time()

        for bus_id in range(1, FLEET_SIZE + 1):
            # 1. Envío periódico de posición (siempre)
            if current_time - last_position_send[bus_id-1] >= POSITION_INTERVAL:
                pos_data = generate_position_update(bus_id)
                topic_pos = f"{BASE_TOPIC}/{bus_id}/position"

                payload_pos = json.dumps(pos_data, ensure_ascii=False)
                client.publish(topic_pos, payload_pos, qos=0, retain=False)

                print(f"📍 Posición enviada - Bus {bus_id}")
                print(json.dumps(pos_data, indent=2))

                last_position_send[bus_id-1] = current_time

            # 2. Generar y evaluar telemetría completa (solo si hay riesgo se envía)
            full_data = simulate_full_telemetry(bus_id)

            if full_data["events"]:  # Si hay al menos un evento crítico
                topic_alert = f"{BASE_TOPIC}/{bus_id}/alertas"
                payload_alert = json.dumps(full_data, ensure_ascii=False)

                print(f"🚨 RIESGO DETECTADO - Bus {bus_id}")
                print(json.dumps(full_data, indent=2, ensure_ascii=False))

                result = client.publish(topic_alert, payload_alert, qos=1, retain=False)

                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    print("   ✓ Alerta publicada exitosamente")
                else:
                    print(f"   ✗ Error al publicar alerta - rc={result.rc}")

        time.sleep(EVENT_CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        run_simulator()
    except KeyboardInterrupt:
        print("\nSimulador detenido por el usuario")
        client.loop_stop()
        client.disconnect()
        print("Conexión MQTT cerrada correctamente")