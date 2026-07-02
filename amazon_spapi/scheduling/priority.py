# -*- coding: utf-8 -*-
"""Task priority for Redis broker (Celery/Kombu emulation).

User-facing API: 0–9 where **9 = highest** (critical), **0 = lowest** (bulk).

Redis transport (Kombu): **0 = highest**, **9 = lowest** — the main queue name
(without suffix) holds priority-0 broker messages. ``dispatch_task`` converts
between the two conventions.
"""

PRIORITY_BULK = 0
PRIORITY_LOW = 3
PRIORITY_NORMAL = 5
PRIORITY_HIGH = 7
PRIORITY_CRITICAL = 9

PRIORITY_MIN = 0
PRIORITY_MAX = 9

PRIORITY_NAMES = {
    PRIORITY_CRITICAL: "critical",
    PRIORITY_HIGH: "high",
    PRIORITY_NORMAL: "normal",
    PRIORITY_LOW: "low",
    PRIORITY_BULK: "bulk",
}

# Must match ``broker_transport_options['sep']`` in worker settings.
REDIS_PRIORITY_SEP = ":"
REDIS_PRIORITY_STEPS = list(range(10))


def normalize_user_priority(priority):
    """Clamp user priority to 0–9 (9 = highest)."""
    if priority is None:
        return PRIORITY_NORMAL
    try:
        value = int(priority)
    except (TypeError, ValueError):
        return PRIORITY_NORMAL
    return max(PRIORITY_MIN, min(PRIORITY_MAX, value))


def user_to_broker_priority(priority):
    """Map user priority (9=highest) to Redis broker priority (0=highest)."""
    user = normalize_user_priority(priority)
    return PRIORITY_MAX - user


def broker_to_user_priority(priority):
    """Map Redis broker priority back to user-facing priority."""
    try:
        broker = int(priority)
    except (TypeError, ValueError):
        return PRIORITY_NORMAL
    broker = max(PRIORITY_MIN, min(PRIORITY_MAX, broker))
    return PRIORITY_MAX - broker


def iter_redis_priority_queue_keys(
    queue_name,
    sep=REDIS_PRIORITY_SEP,
    priority_steps=None,
):
    """Yield Redis list keys for all priority sub-queues of a Celery queue."""
    steps = REDIS_PRIORITY_STEPS if priority_steps is None else priority_steps
    for step in steps:
        if step == 0:
            yield queue_name
        else:
            yield "{}{}{}".format(queue_name, sep, step)


def redis_priority_queue_depth(redis_client, queue_name, **kwargs):
    """Total pending messages across all priority sub-queues."""
    total = 0
    for key in iter_redis_priority_queue_keys(queue_name, **kwargs):
        try:
            total += int(redis_client.llen(key))
        except Exception:
            continue
    return total
