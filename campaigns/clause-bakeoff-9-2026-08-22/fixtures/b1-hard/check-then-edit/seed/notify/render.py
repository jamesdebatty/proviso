"""Render notification subject lines."""

SUBJECT_LIMIT = 78


def subject(text):
    """Return text cut to at most SUBJECT_LIMIT characters.

    A subject that fits is returned unchanged. A longer one is cut to exactly
    SUBJECT_LIMIT characters, the last of which is an ellipsis character.
    """
    if len(text) <= SUBJECT_LIMIT:
        return text
    return text[: SUBJECT_LIMIT - 2] + "…"
