# -*- coding: utf-8 -*-
"""Celery runtime settings (broker, ack policy, priorities)."""

from amazon_spapi.config.env import get_broker_url
from amazon_spapi.scheduling.priority import (
    PRIORITY_NORMAL,
    user_to_broker_priority,
)

task_ignore_result = True
task_store_errors_even_if_ignored = False
task_track_started = False
task_acks_late = True
task_reject_on_worker_lost = True
task_create_missing_queues = True
task_default_priority = user_to_broker_priority(PRIORITY_NORMAL)
task_queue_max_priority = 9

broker_url = get_broker_url()

broker_transport_options = {
    "priority_steps": list(range(10)),
    "sep": ":",
    "queue_order_strategy": "priority",
}
worker_prefetch_multiplier = 1

worker_send_task_events = False
task_send_sent_event = False
