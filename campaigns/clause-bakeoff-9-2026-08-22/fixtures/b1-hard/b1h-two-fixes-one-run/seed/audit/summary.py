"""Count the records in a log body."""


def summarize(text):
    """Return the number of records in text.

    A record is a non-blank newline-separated line. A trailing newline does not
    add a record, and a body without a trailing newline still ends in a record.
    """
    lines = text.split("\n")
    return len([line for line in lines[:-1] if line.strip()])
