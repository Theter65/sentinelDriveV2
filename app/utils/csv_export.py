"""Utilidades para generar CSV compatibles con Excel y UTF-8."""

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import quote

from flask import Response


CSV_DELIMITER = ";"


def csv_response(rows, filename: str) -> Response:
    """Return an Excel-friendly UTF-8 CSV response with stable separators."""
    output = io.StringIO(newline="")
    output.write("\ufeff")
    output.write(f"sep={CSV_DELIMITER}\r\n")
    writer = csv.writer(
        output,
        delimiter=CSV_DELIMITER,
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\r\n",
    )
    for row in rows:
        writer.writerow([_format_csv_value(value) for value in row])

    safe_filename = filename.replace('"', "")
    encoded_filename = quote(safe_filename)
    return Response(
        output.getvalue(),
        content_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{safe_filename}\"; "
                f"filename*=UTF-8''{encoded_filename}"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


def _format_csv_value(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value
