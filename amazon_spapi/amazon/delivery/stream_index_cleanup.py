# -*- coding: utf-8 -*-
"""Remove ASINs from legacy per-MP and unified bucket stream indices."""

from __future__ import annotations

import logging
from typing import Iterable, List, Sequence

from amazon_spapi.amazon.delivery.indices import (
    default_asin_index_name,
    default_invalid_offer_asin_index_name,
    default_no_offer_asin_index_name,
    default_unuploadable_asin_index_name,
)
from amazon_spapi.amazon.delivery.bucket_indices import (
    bucket_doc_ids,
    bucket_index_for_suffix,
)

logger = logging.getLogger(__name__)


def _normalize_asins(asins: Iterable[str]) -> List[str]:
    return [str(asin).strip() for asin in asins if asin and str(asin).strip()]


def delete_asins_from_no_info_indices(
    product_service,
    marketplace: str,
    asins: Iterable[str],
) -> int:
    """Delete ASINs from ``amz_asins_{mp}_no_info`` and ``amz_asin_bucket_no_info``."""
    return _delete_asins_from_legacy_and_bucket(
        product_service,
        marketplace,
        asins,
        legacy_index=default_asin_index_name(marketplace),
        bucket_suffix="no_info",
        label="no_info",
    )


def delete_asins_from_no_offer_indices(
    product_service,
    marketplace: str,
    asins: Iterable[str],
) -> int:
    """Delete ASINs from ``amz_asins_{mp}_no_offer`` and ``amz_asin_bucket_no_offer``."""
    return _delete_asins_from_legacy_and_bucket(
        product_service,
        marketplace,
        asins,
        legacy_index=default_no_offer_asin_index_name(marketplace),
        bucket_suffix="no_offer",
        label="no_offer",
    )


def delete_asins_from_unuploadable_indices(
    product_service,
    marketplace: str,
    asins: Iterable[str],
) -> int:
    """Delete ASINs from ``amz_asins_{mp}_unuploadable`` and ``amz_asin_bucket_unuploadable``."""
    return _delete_asins_from_legacy_and_bucket(
        product_service,
        marketplace,
        asins,
        legacy_index=default_unuploadable_asin_index_name(marketplace),
        bucket_suffix="unuploadable",
        label="unuploadable",
    )


def delete_asins_from_invalid_offer_indices(
    product_service,
    marketplace: str,
    asins: Iterable[str],
) -> int:
    """Delete ASINs from ``amz_asins_{mp}_invalid_offer`` and ``amz_asin_bucket_invalid_offer``."""
    return _delete_asins_from_legacy_and_bucket(
        product_service,
        marketplace,
        asins,
        legacy_index=default_invalid_offer_asin_index_name(marketplace),
        bucket_suffix="invalid_offer",
        label="invalid_offer",
    )


def prune_already_fetched_no_info_asins(
    product_service,
    marketplace: str,
    scanned_asins: Sequence[str],
    asins_still_needed: Sequence[str],
) -> int:
    """Remove ASINs that already have fresh catalog and no longer need enqueue."""
    still_needed = set(asins_still_needed)
    fetched = [asin for asin in scanned_asins if asin not in still_needed]
    return delete_asins_from_no_info_indices(product_service, marketplace, fetched)


def prune_already_fetched_no_offer_asins(
    product_service,
    marketplace: str,
    scanned_asins: Sequence[str],
    asins_still_needed: Sequence[str],
) -> int:
    """Remove ASINs that already have fresh offers and no longer need enqueue."""
    still_needed = set(asins_still_needed)
    fetched = [asin for asin in scanned_asins if asin not in still_needed]
    return delete_asins_from_no_offer_indices(product_service, marketplace, fetched)


def _delete_asins_from_legacy_and_bucket(
    product_service,
    marketplace: str,
    asins: Iterable[str],
    *,
    legacy_index: str,
    bucket_suffix: str,
    label: str,
) -> int:
    asin_list = _normalize_asins(asins)
    if not asin_list:
        return 0

    mp = (marketplace or "").strip().lower()
    bucket_index = bucket_index_for_suffix(bucket_suffix)
    deleted = 0

    try:
        product_service.ensure_indice(legacy_index)
        product_service.delete_products(legacy_index, asin_list)
        deleted += len(asin_list)
    except Exception:
        logger.exception(
            "[StreamIndexCleanup] failed legacy delete marketplace=%s index=%s count=%s",
            mp,
            legacy_index,
            len(asin_list),
        )

    try:
        product_service.ensure_indice(bucket_index)
        doc_ids = bucket_doc_ids(mp, asin_list)
        product_service.delete_products(bucket_index, doc_ids)
        deleted += len(doc_ids)
    except Exception:
        logger.exception(
            "[StreamIndexCleanup] failed bucket delete marketplace=%s index=%s count=%s",
            mp,
            bucket_index,
            len(asin_list),
        )

    if deleted:
        logger.info(
            "[StreamIndexCleanup] marketplace=%s label=%s deleted_docs=%s asins=%s",
            mp,
            label,
            deleted,
            len(asin_list),
        )
    return deleted
