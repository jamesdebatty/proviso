"""Row rendering helpers."""

WIDTH = 24


def render_row(row):
    label = str(row.get("label", ""))[:WIDTH]
    return f"{label:<{WIDTH}}{row.get('value', '')}"
