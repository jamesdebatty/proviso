"""Layer a per-environment override on top of a base manifest."""


def deep_merge(base, override):
    """Return base with override layered on top.

    Where both sides hold a dictionary the two are merged key by key, so an
    override that sets one nested key leaves the base's other nested keys in
    place. Any other value in override replaces the base's value. Neither
    argument is modified.
    """
    result = dict(base)
    for key, value in override.items():
        result[key] = value
    return result
