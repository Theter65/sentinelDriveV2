# app/mqtt/deduplication.py - Filtro de deduplicación de mensajes MQTT
#
# Evita procesar mensajes duplicados en memoria usando un fingerprint
# compuesto por bus_id + timestamp + tipo de evento + valor + clave extra.
# Los fingerprints expiran automáticamente tras un TTL (10s por defecto).
# Máximo 10000 entradas en caché para evitar memory leak.
# =============================================================================

import threading
import time
from datetime import datetime

from app.utils.logging import get_logger


logger = get_logger(__name__)

_processed_messages = {}
_lock = threading.Lock()
DEFAULT_TTL_SECONDS = 10
MAX_CACHE_SIZE = 10000


def _cleanup(now_monotonic: float) -> None:
    expired_keys = [
        key for key, expires_at in _processed_messages.items() if expires_at <= now_monotonic
    ]
    for key in expired_keys:
        _processed_messages.pop(key, None)


def should_process_message(
    bus_id: int,
    timestamp: datetime,
    event_type: str = None,
    value=None,
    extra_key: str = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> bool:
    """Return False when a recently processed equivalent message is detected."""
    parts = [str(bus_id), timestamp.isoformat()]
    if event_type:
        parts.append(str(event_type))
    if value is not None:
        parts.append(str(value))
    if extra_key:
        parts.append(str(extra_key))
    fingerprint = "|".join(parts)

    now_monotonic = time.monotonic()
    with _lock:
        _cleanup(now_monotonic)
        if fingerprint in _processed_messages:
            logger.debug("Duplicado detectado: %s", fingerprint)
            return False
        _processed_messages[fingerprint] = now_monotonic + ttl_seconds
        if len(_processed_messages) > MAX_CACHE_SIZE:
            _cleanup(now_monotonic)
            if len(_processed_messages) > MAX_CACHE_SIZE:
                _processed_messages.clear()
                logger.info("Cache de deduplicacion limpiado por tamano")
    return True
