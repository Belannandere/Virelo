import csv
import io

from app.models import InvoiceRecord


CSV_HEADER = [
    "supplier_name",
    "invoice_number",
    "invoice_date",
    "currency",
    "subtotal",
    "tax",
    "total",
]


def _row_from_record(record: InvoiceRecord) -> list:
    return [
        record.supplier_name or "",
        record.invoice_number or "",
        record.invoice_date or "",
        record.currency or "",
        _fmt_number(record.subtotal),
        _fmt_number(record.tax),
        _fmt_number(record.total),
    ]


def _fmt_number(value) -> str:
    """None → пустая строка, число → строка без хвостовых нулей."""
    if value is None:
        return ""
    # 1900.0 → "1900", 1900.5 → "1900.5"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def records_to_csv(records: list[InvoiceRecord]) -> str:
    """Собирает CSV-строку из списка записей инвойсов."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for record in records:
        writer.writerow(_row_from_record(record))
    return buf.getvalue()