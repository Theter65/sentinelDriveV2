from datetime import datetime
from zoneinfo import ZoneInfo


ECUADOR_TZ = ZoneInfo("America/Guayaquil")


def ecuador_now() -> datetime:
    """Return a timezone-aware timestamp in Ecuador local time."""
    return datetime.now(ECUADOR_TZ)
