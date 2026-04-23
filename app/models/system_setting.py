from app.extensions import db
from app.utils.time import ecuador_now


class SystemSetting(db.Model):
    """Key/value storage for runtime configuration editable from the UI."""

    __tablename__ = "system_setting"

    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=ecuador_now,
        onupdate=ecuador_now,
        nullable=False,
    )

    @classmethod
    def get_value(cls, key: str, default=None):
        row = db.session.get(cls, key)
        if row is None or row.value in (None, ""):
            return default
        return row.value

    @classmethod
    def set_value(cls, key: str, value):
        row = db.session.get(cls, key)
        if row is None:
            row = cls(key=key)
        row.value = value
        db.session.add(row)
        return row

    @classmethod
    def delete_value(cls, key: str):
        row = db.session.get(cls, key)
        if row is not None:
            db.session.delete(row)
