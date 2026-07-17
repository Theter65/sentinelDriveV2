# app/models/event.py - Modelo de eventos operativos
#
# Almacena eventos críticos recibidos por MQTT (exceso velocidad,
# frenado brusco, curva peligrosa,
# otros). Cada evento tiene value/value1/value2, descripción opcional
# y coordenadas. Resuelve unidades según tipo de evento.
# =============================================================================

from app.extensions import db
from app.utils.time import ecuador_now


class Event(db.Model):
    """Registro de eventos criticos detectados."""

    __tablename__ = "event"
    __table_args__ = (
        db.Index("ix_event_bus_timestamp", "bus_id", "timestamp"),
    )

    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(
        db.Integer,
        db.ForeignKey("bus.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type = db.Column(db.String(50), nullable=False, index=True)
    value = db.Column(db.Float(precision=2), nullable=True)
    value1 = db.Column(db.Float(precision=2), nullable=True)
    value2 = db.Column(db.Float(precision=2), nullable=True)
    # Campo opcional para eventos extendidos (p. ej. tipo "Otros" con sensores extra)
    description = db.Column(db.String(300), nullable=True)
    latitude = db.Column(db.Float(precision=8), nullable=True)
    longitude = db.Column(db.Float(precision=8), nullable=True)
    timestamp = db.Column(
        db.DateTime(timezone=False),
        nullable=False,
        default=ecuador_now,
        index=True,
    )

    @property
    def resolved_value1(self):
        if self.value1 is not None:
            return self.value1
        return self.value

    @property
    def resolved_value(self):
        return self.resolved_value1

    @property
    def value_label(self):
        lines = self.value_lines
        if not lines:
            return "N/A"
        return " | ".join(lines)

    @property
    def value_lines(self):
        unit1, unit2 = self._units_for_display()
        lines = []
        if self.resolved_value1 is not None:
            lines.append(self._format_value_with_unit(self.resolved_value1, unit1))
        if self.value2 is not None:
            lines.append(self._format_value_with_unit(self.value2, unit2))
        return lines

    def _units_for_display(self):
        mapping = {
            "Exceso de velocidad": ("km/h", None),
            "Frenado brusco": ("m/s²", None),
            "Curva peligrosa": ("m/s²", None),
            "Otros": (None, None),
        }
        return mapping.get(self.type, (None, None))

    @staticmethod
    def _format_number(value):
        text = f"{float(value):.2f}"
        return text.rstrip("0").rstrip(".")

    def _format_value_with_unit(self, value, unit):
        number = self._format_number(value)
        return f"{number} {unit}" if unit else number

    def __repr__(self):
        return f"<Event {self.type} en bus {self.bus_id} a {self.timestamp}>"
