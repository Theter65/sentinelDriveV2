import logging
import os
import sys
import threading

from dotenv import load_dotenv

from app import create_app
from app.models.init_data import initialize_database
from app.mqtt.subscriber import start_mqtt_subscriber
from app.utils.logging import get_logger


load_dotenv()

logger = get_logger(__name__)
log_level = logging.DEBUG if os.getenv("FLASK_DEBUG", "False").lower() == "true" else logging.INFO
logger.setLevel(log_level)

app = create_app()


def run_mqtt_worker():
    """Proceso dedicado para Render/Raspberry: solo escucha MQTT."""
    logger.info("Iniciando worker MQTT dedicado")
    with app.app_context():
        initialize_database()
        logger.info("Base de datos verificada para worker MQTT")
    start_mqtt_subscriber(app)


def run_development_server():
    """Servidor local: Flask + suscriptor MQTT en background."""
    try:
        with app.app_context():
            initialize_database()
            logger.info("Datos iniciales verificados/creados")

        mqtt_thread = threading.Thread(
            target=start_mqtt_subscriber,
            args=(app,),
            daemon=True,
            name="MQTT-Listener",
        )
        mqtt_thread.start()
        logger.info("Suscriptor MQTT iniciado en background")

        logger.warning("Servidor Flask iniciado (debug=%s). Accede en http://0.0.0.0:5000", app.debug)
        app.run(
            debug=app.config["DEBUG"],
            host="0.0.0.0",
            port=5000,
            threaded=True,
        )
    except KeyboardInterrupt:
        logger.info("Servidor detenido por el usuario (Ctrl+C)")
    except Exception as exc:
        logger.critical("Error critico al iniciar el servidor: %s", exc, exc_info=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in {"mqtt-worker", "worker", "mqtt"}:
        run_mqtt_worker()
    else:
        run_development_server()
