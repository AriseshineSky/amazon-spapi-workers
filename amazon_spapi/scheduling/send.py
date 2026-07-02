# -*- coding: utf-8 -*-
"""Dispatch work items to the Celery broker with normalized priority."""

from amazon_spapi.scheduling.priority import (
    PRIORITY_BULK,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NAMES,
    PRIORITY_NORMAL,
    normalize_user_priority,
    user_to_broker_priority,
)

__all__ = [
    "PRIORITY_BULK",
    "PRIORITY_CRITICAL",
    "PRIORITY_HIGH",
    "PRIORITY_LOW",
    "PRIORITY_NORMAL",
    "PRIORITY_NAMES",
    "dispatch_task",
    "normalize_user_priority",
]


def dispatch_task(
    task,
    args=None,
    kwargs=None,
    queue=None,
    connection=None,
    priority=None,
    **options,
):
    send_kwargs = dict(options)
    if queue is not None:
        send_kwargs["queue"] = queue
    if connection is not None:
        send_kwargs["connection"] = connection
    send_kwargs["priority"] = user_to_broker_priority(priority)
    return task.apply_async(args=args, kwargs=kwargs, **send_kwargs)
