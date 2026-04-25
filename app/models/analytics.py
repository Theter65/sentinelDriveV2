from app.extensions import db
from app.utils.time import ecuador_now


class AnalyticsRun(db.Model):
    """Registro de cada ejecucion del modulo de analisis estadistico."""

    __tablename__ = "analytics_runs"
    __table_args__ = (
        db.Index("ix_analytics_run_bus_dates", "bus_id", "date_from", "date_to"),
    )

    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(
        db.Integer,
        db.ForeignKey("bus.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    date_from = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    date_to = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    speed_limit = db.Column(db.Float, nullable=False)
    generated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=ecuador_now,
        index=True,
    )
    status = db.Column(db.String(20), nullable=False, default="completed", index=True)
    notes = db.Column(db.Text, nullable=True)

    summary = db.relationship(
        "VehicleStatisticsSummary",
        backref="analytics_run",
        lazy=True,
        cascade="all, delete-orphan",
        uselist=False,
    )
    event_type_statistics = db.relationship(
        "EventTypeStatistic",
        backref="analytics_run",
        lazy=True,
        cascade="all, delete-orphan",
    )
    hourly_event_statistics = db.relationship(
        "HourlyEventStatistic",
        backref="analytics_run",
        lazy=True,
        cascade="all, delete-orphan",
    )
    speed_histogram_bins = db.relationship(
        "SpeedHistogramBin",
        backref="analytics_run",
        lazy=True,
        cascade="all, delete-orphan",
    )
    event_magnitude_statistics = db.relationship(
        "EventMagnitudeStatistic",
        backref="analytics_run",
        lazy=True,
        cascade="all, delete-orphan",
    )


class VehicleStatisticsSummary(db.Model):
    """Resumen descriptivo principal por ejecucion analitica."""

    __tablename__ = "vehicle_statistics_summary"

    id = db.Column(db.Integer, primary_key=True)
    analytics_run_id = db.Column(
        db.Integer,
        db.ForeignKey("analytics_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    bus_id = db.Column(
        db.Integer,
        db.ForeignKey("bus.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    date_from = db.Column(db.DateTime(timezone=True), nullable=False)
    date_to = db.Column(db.DateTime(timezone=True), nullable=False)
    total_locations = db.Column(db.Integer, nullable=False, default=0)
    total_events = db.Column(db.Integer, nullable=False, default=0)
    speed_min = db.Column(db.Float, nullable=False, default=0)
    speed_max = db.Column(db.Float, nullable=False, default=0)
    speed_avg = db.Column(db.Float, nullable=False, default=0)
    speed_median = db.Column(db.Float, nullable=False, default=0)
    speed_p85 = db.Column(db.Float, nullable=False, default=0)
    speed_p95 = db.Column(db.Float, nullable=False, default=0)
    speed_stddev = db.Column(db.Float, nullable=False, default=0)
    speed_cv = db.Column(db.Float, nullable=False, default=0)
    speeding_count = db.Column(db.Integer, nullable=False, default=0)
    speeding_percentage = db.Column(db.Float, nullable=False, default=0)
    ico_score = db.Column(db.Float, nullable=False, default=0)
    ico_level = db.Column(db.String(20), nullable=False, default="Bajo")
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=ecuador_now,
        index=True,
    )


class EventTypeStatistic(db.Model):
    """Eventos agrupados por tipo para una ejecucion analitica."""

    __tablename__ = "event_type_statistics"
    __table_args__ = (
        db.Index("ix_event_type_stats_run_type", "analytics_run_id", "event_type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    analytics_run_id = db.Column(
        db.Integer,
        db.ForeignKey("analytics_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = db.Column(db.String(50), nullable=False)
    event_count = db.Column(db.Integer, nullable=False, default=0)
    event_percentage = db.Column(db.Float, nullable=False, default=0)


class HourlyEventStatistic(db.Model):
    """Eventos agrupados por hora del dia."""

    __tablename__ = "hourly_event_statistics"
    __table_args__ = (
        db.Index("ix_hourly_event_stats_run_hour", "analytics_run_id", "hour"),
    )

    id = db.Column(db.Integer, primary_key=True)
    analytics_run_id = db.Column(
        db.Integer,
        db.ForeignKey("analytics_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hour = db.Column(db.Integer, nullable=False)
    total_events = db.Column(db.Integer, nullable=False, default=0)


class SpeedHistogramBin(db.Model):
    """Distribucion de velocidades por rangos de 10 km/h."""

    __tablename__ = "speed_histogram_bins"
    __table_args__ = (
        db.Index("ix_speed_histogram_run_bin", "analytics_run_id", "bin_start"),
    )

    id = db.Column(db.Integer, primary_key=True)
    analytics_run_id = db.Column(
        db.Integer,
        db.ForeignKey("analytics_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bin_start = db.Column(db.Float, nullable=False)
    bin_end = db.Column(db.Float, nullable=True)
    frequency = db.Column(db.Integer, nullable=False, default=0)
    percentage = db.Column(db.Float, nullable=False, default=0)


class EventMagnitudeStatistic(db.Model):
    """Magnitudes basicas por tipo de evento critico."""

    __tablename__ = "event_magnitude_statistics"
    __table_args__ = (
        db.Index("ix_event_magnitude_run_type", "analytics_run_id", "event_type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    analytics_run_id = db.Column(
        db.Integer,
        db.ForeignKey("analytics_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = db.Column(db.String(50), nullable=False)
    max_value = db.Column(db.Float, nullable=False, default=0)
    avg_value = db.Column(db.Float, nullable=False, default=0)
    count = db.Column(db.Integer, nullable=False, default=0)
