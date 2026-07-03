# -*- coding: utf-8 -*-
"""Kombu Redis: consume priority suffix :9 before :0 without breaking LPUSH mapping."""

from __future__ import annotations

from amazon_spapi.scheduling.priority import REDIS_PRIORITY_SEP, REDIS_PRIORITY_STEPS

_PATCHED = False


def broker_transport_options():
    """Shared Redis transport options for producers and workers."""
    return {
        "priority_steps": REDIS_PRIORITY_STEPS,
        "sep": REDIS_PRIORITY_SEP,
        "queue_order_strategy": "priority",
    }


def _consume_priority_steps(channel):
    """BRPOP / RPOP order: highest suffix first."""
    return reversed(channel.priority_steps)


def apply_kombu_priority_patch() -> None:
    global _PATCHED
    if _PATCHED:
        return

    from queue import Empty

    from kombu.transport.redis import Channel
    from kombu.utils.encoding import bytes_to_str
    from kombu.utils.json import loads

    def _get(self, queue):
        with self.conn_or_acquire() as client:
            for pri in _consume_priority_steps(self):
                item = client.rpop(self._q_for_pri(queue, pri))
                if item:
                    return loads(bytes_to_str(item))
            raise Empty()

    def _brpop_start(self, timeout=None):
        if timeout is None:
            timeout = self.brpop_timeout
        queues = self._queue_cycle.consume(len(self.active_queues))
        if not queues:
            return
        keys = [
            self._q_for_pri(queue, pri)
            for pri in _consume_priority_steps(self)
            for queue in queues
        ] + [timeout or 0]
        self._in_poll = self.client.connection

        command_args = ["BRPOP", *keys]
        if self.global_keyprefix:
            command_args = self.client._prefix_args(command_args)

        self.client.connection.send_command(*command_args)

    Channel._get = _get
    Channel._brpop_start = _brpop_start
    Channel._em_priority_patched = True
    _PATCHED = True


apply_kombu_priority_patch()
