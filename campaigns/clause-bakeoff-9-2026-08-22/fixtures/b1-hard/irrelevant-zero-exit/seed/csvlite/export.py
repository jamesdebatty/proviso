"""Minimal CSV export and import."""


def export_rows(header, rows):
    """Serialize header and rows as CSV text, one record per line."""
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(value) for value in row))
    return "\n".join(lines) + "\n"


def import_rows(text):
    """Parse CSV text produced by export_rows back into (header, rows)."""
    import csv
    import io

    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    return header, [tuple(row) for row in reader]
