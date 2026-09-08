"""Plan a job run under its configuration."""


def plan(config, items):
    """Split ``items`` into one batch per worker and compute the time budget."""
    per_worker = -(-len(items) // config.workers)
    batches = [items[i:i + per_worker] for i in range(0, len(items), per_worker)]
    attempts = config.retries + 1
    return {
        "batches": batches,
        "attempts": attempts,
        "budget_seconds": config.timeout_seconds * attempts,
    }
