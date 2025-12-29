from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Cache global para deduplicación (Message ID + timestamp fallback)
processed_messages = set()
EVENT_DEDUP_SECONDS = 10  # Ventana temporal anti-duplicados (ajustable)

def should_process_message(bus_id: int, timestamp: datetime, event_type: str = None, value: float = None) -> bool:
    """
    Determina si un mensaje debe procesarse o es duplicado.
    Usa Message ID (si disponible) + ventana temporal como fallback.
    """
    # Clave temporal (bus_id + timestamp + tipo + valor)
    temp_key = f"{bus_id}_{timestamp.isoformat()}"
    if event_type:
        temp_key += f"_{event_type}_{value or 'none'}"

    # Si ya está en cache → duplicado
    if temp_key in processed_messages:
        logger.debug(f"Duplicado detectado (temporal): bus {bus_id} @ {timestamp}")
        return False

    # Registrar como procesado
    processed_messages.add(temp_key)

    # Limpieza periódica del cache (evitar memoria infinita)
    if len(processed_messages) > 10000:
        processed_messages.clear()
        logger.info("Cache de deduplicación limpiado")

    return True