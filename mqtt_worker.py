"""Entrada corta para ejecutar unicamente el worker MQTT en despliegues separados."""

from run import run_mqtt_worker


if __name__ == "__main__":
    run_mqtt_worker()
