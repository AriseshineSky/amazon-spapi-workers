# -*- coding: utf-8 -*-
"""Amazon marketplace IDs and locale helpers for SP-API."""

MARKETPLACE_IDS = {
    "US": "ATVPDKIKX0DER",
    "CA": "A2EUQ1WTGCTBG2",
    "MX": "A1AM78C64UM0Y8",
    "BR": "A2Q3Y263D00KWC",
    "UK": "A1F83G8C2ARO7P",
    "DE": "A1PA6795UKMFR9",
    "ES": "A1RKKUPIHCS9HS",
    "FR": "A13V1IB3VIYZZH",
    "IT": "APJ6JRA9NG5V4",
    "BE": "AMEN7PMS3EDWL",
    "NL": "A1805IZSGTT6HS",
    "SE": "A2NODRKZP88ZB9",
    "ZA": "AE08WJ6YKNBMC",
    "PL": "A1C3SOZRARQ6R3",
    "EG": "ARBP9OOSHTCHU",
    "TR": "A33AVAJ2PDY3EV",
    "SA": "A17E79C6D8DWNP",
    "AE": "A2VIGQ35RCS4UG",
    "IN": "A21TJRUUN4KGV",
    "SG": "A19VAU5U5O7RUS",
    "AU": "A39IBJ37TRP1C6",
    "JP": "A1VC38T7YXB528",
}

MARKETPLACE_COUNTRY_MAPPING = {
    "A2EUQ1WTGCTBG2": "ca",
    "A1AM78C64UM0Y8": "mx",
    "ATVPDKIKX0DER": "us",
    "A2Q3Y263D00KWC": "br",
    "A1PA6795UKMFR9": "de",
    "A1RKKUPIHCS9HS": "es",
    "A13V1IB3VIYZZH": "fr",
    "APJ6JRA9NG5V4": "it",
    "A1F83G8C2ARO7P": "uk",
    "A21TJRUUN4KGV": "in",
    "A1VC38T7YXB528": "jp",
    "A39IBJ37TRP1C6": "au",
    "A2VIGQ35RCS4UG": "ae",
    "A33AVAJ2PDY3EV": "tr",
    "A19VAU5U5O7RUS": "sg",
    "A1805IZSGTT6HS": "nl",
    "A17E79C6D8DWNP": "sa",
    "AMEN7PMS3EDWL": "be",
    "A2NODRKZP88ZB9": "se",
    "A1C3SOZRARQ6R3": "pl",
    "AE08WJ6YKNBMC": "za",
    "ARBP9OOSHTCHU": "eg",
}


MARKETPLACE_REGIONS = {
    "US": "NA",
    "CA": "NA",
    "MX": "NA",
    "BR": "NA",
    "UK": "EU",
    "DE": "EU",
    "ES": "EU",
    "FR": "EU",
    "IT": "EU",
    "BE": "EU",
    "NL": "EU",
    "SE": "EU",
    "ZA": "EU",
    "PL": "EU",
    "EG": "EU",
    "TR": "EU",
    "SA": "EU",
    "AE": "EU",
    "IN": "EU",
    "SG": "FE",
    "AU": "FE",
    "JP": "FE",
}


def marketplace_locale(marketplace: str) -> str | None:
    marketplace = marketplace.upper()
    if marketplace in ("UK", "DE", "BE"):
        return "en_GB"
    if marketplace == "FR":
        return "fr_FR"
    if marketplace == "IT":
        return "it_IT"
    if marketplace == "ES":
        return "es_ES"
    if marketplace in ("US", "JP"):
        return "en_US"
    if marketplace == "TR":
        return "tr_TR"
    if marketplace == "AU":
        return "en_AU"
    if marketplace == "MX":
        return "es_MX"
    if marketplace == "NL":
        return "nl_NL"
    if marketplace == "SE":
        return "sv_SE"
    if marketplace == "PL":
        return "pl_PL"
    if marketplace == "SG":
        return "en_SG"
    if marketplace == "CA":
        return "en_CA"
    if marketplace in ("EG", "SA", "AE"):
        return "en_AE"
    if marketplace == "IN":
        return "en_IN"
    if marketplace == "IE":
        return "en_IE"
    return None


def marketplace_region(marketplace: str) -> str | None:
    return MARKETPLACE_REGIONS.get((marketplace or "").upper())
