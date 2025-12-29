# =============================================================================
# run.py - Punto de entrada principal de SENTINLDRIVE
#
# Responsabilidades únicas:
# - Crear la aplicación Flask
# - Inicializar datos de prueba (solo una vez, con contexto completo)
# - Iniciar el suscriptor MQTT en background
# - Ejecutar el servidor Flask
# =============================================================================

import os
from app import create_app
from app.mqtt.subscriber import start_mqtt_subscriber
from app.utils.logging import get_logger
from app.models.init_data import initialize_database
import threading
import logging
from logging.handlers import RotatingFileHandler

# Cargar variables de entorno
from dotenv import load_dotenv
load_dotenv()

# Configuración de logging (consola + archivo rotativo)
logger = get_logger(__name__)

# Nivel de logging (DEBUG en desarrollo, INFO en producción)
log_level = logging.DEBUG if os.getenv('FLASK_DEBUG', 'False').lower() == 'true' else logging.INFO
logger.setLevel(log_level)

# Crear la aplicación Flask
app = create_app()

if __name__ == "__main__":
    try:
        with app.app_context():
            initialize_database()
            logger.info("Datos iniciales verificados/creados (admin + correcciones)")

        # Pasa app al thread MQTT
        threading.Thread(
            target=start_mqtt_subscriber,
            args=(app,),  # ← Cambio clave
            daemon=True,
            name="MQTT-Listener"
        ).start()
        logger.info("Suscriptor MQTT iniciado en background (thread daemon)")

        logger.warning(
            "Servidor Flask iniciado (debug=%s). Accede en http://0.0.0.0:5000",
            app.debug
        )

        app.run(
            debug=False,
            host='0.0.0.0',
            port=5000,
            threaded=True
        )

    except KeyboardInterrupt:
        logger.info("Servidor detenido por el usuario (Ctrl+C)")
    except Exception as e:
        logger.critical(f"Error crítico al iniciar el servidor: {e}", exc_info=True)