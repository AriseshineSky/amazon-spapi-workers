# -*- coding: utf-8 -*-
"""ASIN validation helpers."""

import re


def is_asin_valid(asin):
    return bool(
        asin
        and not asin.isspace()
        and re.match(
            r"[0-9]{10}|[0-9]{9}[0-9X]{1}|[A-Z]{1}[0-9A-Z]{9}",
            asin,
        )
    )


def pad_asin(asin):
    if len(asin) < 10 and not asin.lower().startswith("b"):
        return "{0:0>10}".format(asin)
    return asin
