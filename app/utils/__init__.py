# app/utils/__init__.py - Utilidades compartidas
#
# Expone las funciones y constantes de uso común en toda la aplicación:
# - get_logger: logger configurado con formato estándar
# - ECUADOR_TZ: zona horaria America/Guayaquil (UTC-5)
# - ecuador_now: timestamp actual con zona horaria
# =============================================================================

from .logging import get_logger
from .time import ECUADOR_TZ, ecuador_now

__all__ = ["ECUADOR_TZ", "ecuador_now", "get_logger"]
