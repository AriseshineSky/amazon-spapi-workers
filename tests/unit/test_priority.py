# -*- coding: utf-8 -*-
"""Tests for Redis-backed Celery priority mapping."""

from amazon_spapi.scheduling.priority import (
    PRIORITY_CRITICAL,
    PRIORITY_NORMAL,
    broker_to_user_priority,
    iter_redis_priority_queue_keys,
    normalize_user_priority,
    user_to_broker_priority,
)
from amazon_spapi.scheduling.send import dispatch_task


class _FakeTask:
    last_priority = None

    def apply_async(self, args=None, kwargs=None, **options):
        _FakeTask.last_priority = options.get("priority")
        return object()


def test_user_priority_9_maps_to_broker_0():
    assert user_to_broker_priority(9) == 0
    assert user_to_broker_priority(PRIORITY_CRITICAL) == 0


def test_user_priority_0_maps_to_broker_9():
    assert user_to_broker_priority(0) == 9


def test_normal_priority_round_trip():
    assert user_to_broker_priority(PRIORITY_NORMAL) == 4
    assert broker_to_user_priority(4) == PRIORITY_NORMAL


def test_normalize_clamps():
    assert normalize_user_priority(99) == 9
    assert normalize_user_priority(-1) == 0
    assert normalize_user_priority(None) == PRIORITY_NORMAL


def test_dispatch_task_converts_priority():
    task = _FakeTask()
    dispatch_task(task, priority=9)
    assert task.last_priority == 0
    dispatch_task(task, priority=1)
    assert task.last_priority == 8


def test_redis_queue_keys():
    keys = list(iter_redis_priority_queue_keys("SpapiItemOffersUpdate_US"))
    assert keys[0] == "SpapiItemOffersUpdate_US"
    assert keys[-1] == "SpapiItemOffersUpdate_US:9"
    assert len(keys) == 10


if __name__ == "__main__":
    test_user_priority_9_maps_to_broker_0()
    test_user_priority_0_maps_to_broker_9()
    test_normal_priority_round_trip()
    test_normalize_clamps()
    test_dispatch_task_converts_priority()
    test_redis_queue_keys()
    print("ok")
