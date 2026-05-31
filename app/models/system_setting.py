# app/models/system_setting.py - Configuración clave/valor persistente
#
# Proporciona almacenamiento tipo key-value para configuración dinámica
# que puede modificarse desde la interfaz de administración sin necesidad
# de reiniciar la aplicación. Se usa para credenciales MQTT, parámetros
# operativos, y estado en tiempo de ejecución.
# =============================================================================

from app.extensions import db
from app.utils.time import ecuador_now


class SystemSetting(db.Model):
    """Almacenamiento clave/valor para configuración en tiempo de ejecución."""

    __tablename__ = "system_setting"

    # Clave única (primary key)
    key = db.Column(db.String(80), primary_key=True)

    # Valor almacenado (texto genérico, el parseo depende del contexto)
    value = db.Column(db.Text, nullable=True)

    # Marca temporal de última modificación
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=ecuador_now,
        onupdate=ecuador_now,
        nullable=False,
    )

    @classmethod
    def get_value(cls, key: str, default=None):
        """Lee un valor persistido por clave. Retorna default si no existe."""
        row = db.session.get(cls, key)
        if row is None or row.value in (None, ""):
            return default
        return row.value

    @classmethod
    def set_value(cls, key: str, value):
        """Crea o actualiza un valor persistido por clave."""
        row = db.session.get(cls, key)
        if row is None:
            row = cls(key=key)
        row.value = value
        db.session.add(row)
        return row

    @classmethod
    def delete_value(cls, key: str):
        """Elimina una clave persistida si existe."""
        row = db.session.get(cls, key)
        if row is not None:
            db.session.delete(row)
