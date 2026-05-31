# app/mqtt/__init__.py - Paquete de integración MQTT
#
# Expone las funciones principales del módulo MQTT:
# - start_mqtt_subscriber: bucle principal de conexión y escucha
# - should_process_message: filtro de deduplicación de mensajes
# =============================================================================

from .subscriber import start_mqtt_subscriber
from .deduplication import should_process_message