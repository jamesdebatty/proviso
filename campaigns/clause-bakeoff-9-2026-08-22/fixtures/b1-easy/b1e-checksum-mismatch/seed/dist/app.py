"""Entry point for the packaged tool."""

from dist.lib import render_row


def main(rows):
    return "\n".join(render_row(row) for row in rows)
