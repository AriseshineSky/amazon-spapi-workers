# -*- coding: utf-8 -*-
"""Tests for ASIN file parsing."""

from amazon_spapi.scheduling.asin_file import extract_asin_from_line


def test_plain_asin_line():
    assert extract_asin_from_line("B09V3KXJPB") == "B09V3KXJPB"


def test_analytics_tsv_json_line():
    line = (
        '31083427\t{"product_id": 31083427, "source": "AMZ_CA", '
        '"source_product_id": "B0FN7JQL57"}'
    )
    assert extract_asin_from_line(line) == "B0FN7JQL57"
    assert extract_asin_from_line(line, source_filter="AMZ_CA") == "B0FN7JQL57"
    assert extract_asin_from_line(line, source_filter="AMZ_US") is None


if __name__ == "__main__":
    test_plain_asin_line()
    test_analytics_tsv_json_line()
    print("ok")
