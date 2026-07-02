# -*- coding: utf-8 -*-
"""Shared application logger."""

import logging
import sys

logger = logging.getLogger("amazon_spapi")
formatter = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
