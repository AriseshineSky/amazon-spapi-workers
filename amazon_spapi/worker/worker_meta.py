# -*- coding: utf-8 -*-
"""Celery worker identity for monitoring documents."""

import os


def build_worker_meta(request):
    node, host = request.hostname.split("@", 1)
    return {
        "worker_id": "{}@{}".format(node, host),
        "node": node,
        "host": host,
        "pid": os.getpid(),
    }
