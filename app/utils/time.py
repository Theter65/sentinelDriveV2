# app/utils/time.py - Zona horaria y timestamps
#
# Define la zona horaria oficial del proyecto (Ecuador, UTC-5).
# Proporciona ecuador_now() para generar timestamps con timezone
# sin depender del servidor. Usa ZoneInfo (Python 3.9+).
# =============================================================================

from datetime import datetime
from zoneinfo import ZoneInfo


ECUADOR_TZ = ZoneInfo("America/Guayaquil")


def ecuador_now() -> datetime:
    """Return a timezone-aware timestamp in Ecuador local time."""
    return datetime.now(ECUADOR_TZ)
