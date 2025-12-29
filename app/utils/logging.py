# =============================================================================
# app/utils/logging.py - Configuración centralizada de logging
#
# Este módulo proporciona loggers consistentes en todo el proyecto.
# - Formato ISO 8601 (compatible con auditoría y normativas)
# - Nivel INFO por defecto (ajustable por entorno)
# - Handler stream (consola) + posibilidad futura de file/rotating
# - Evita configuraciones duplicadas en cada módulo
# =============================================================================

import logging
import sys

def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Devuelve un logger configurado profesionalmente.
    
    Args:
        name: Nombre del módulo (usualmente __name__)
        level: Nivel de logging (por defecto INFO)
    
    Returns:
        Logger configurado y listo para usar
    """
    logger = logging.getLogger(name)
    
    # Evitar configuraciones duplicadas (importante en threads y blueprints)
    if not logger.handlers:
        # Handler principal: consola (stream)
        handler = logging.StreamHandler(sys.stdout)
        
        # Formato estricto ISO 8601 + nivel + mensaje
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
        logger.setLevel(level)
        
        # Evitar propagación a root logger (mejor control)
        logger.propagate = False
    
    return logger