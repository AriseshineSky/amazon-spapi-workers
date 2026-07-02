# -*- coding: utf-8 -*-
"""Backpressure: pause producers when a queue is too deep."""

from amazon_spapi.scheduling.priority import redis_priority_queue_depth


def queue_depth(redis_client, queue_name):
    return redis_priority_queue_depth(redis_client, queue_name)


def should_pause_enqueue(redis_client, queue_name, max_depth):
    return queue_depth(redis_client, queue_name) > max_depth
