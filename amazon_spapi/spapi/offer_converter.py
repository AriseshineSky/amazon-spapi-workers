# -*- coding: utf-8
"""Convert SP-API getItemOffersBatch responses to ES offer documents."""

from datetime import datetime

from amazon_spapi.log import logger
from amazon_spapi.spapi.marketplaces import MARKETPLACE_COUNTRY_MAPPING
from amazon_spapi.spapi.asin import pad_asin


class SpItemOfferBatchConverter:
    def convert(self, data):
        result = {}
        if not data:
            return result

        d = {}
        for item_offers_response in data.payload.get("responses", []):
            cur_time = datetime.strftime(datetime.utcnow(), "%Y-%m-%dT%H:%M:%S")
            asin = item_offers_response.get("request", d).get("Asin")
            if asin is None:
                logger.error(item_offers_response)
                continue

            marketplace_id = item_offers_response.get("request", d).get(
                "MarketplaceId", None
            )
            country = MARKETPLACE_COUNTRY_MAPPING.get(marketplace_id, None)
            condition = item_offers_response.get("request", d).get(
                "ItemCondition", None
            )

            if country is None or condition is None:
                result[asin] = {
                    "asin": asin,
                    "offers": [],
                    "errors": item_offers_response,
                    "summary": "",
                    "time": cur_time,
                }
                logger.error(item_offers_response)
                continue

            errors = item_offers_response.get("body", d).get("errors", None)
            if errors is not None:
                result[asin] = {
                    "asin": asin,
                    "offers": [],
                    "errors": errors,
                    "summary": "",
                    "time": cur_time,
                }
                logger.error(item_offers_response)
                continue

            payload = item_offers_response.get("body", d).get("payload", d)
            asin = pad_asin(asin)
            item_offers_list = payload.get("Offers", [])
            if not isinstance(item_offers_list, list):
                item_offers_list = [item_offers_list]
            offers = []
            for item_offer in item_offers_list:
                subcondition = item_offer.get("SubCondition")
                shipping_price = item_offer.get("Shipping", d).get("Amount")
                product_price = item_offer.get("ListingPrice", d).get("Amount")
                landed_price = round(shipping_price + product_price, 2)

                currency = None
                for item in (
                    item_offer.get("Shipping", d),
                    item_offer.get("ListingPrice", d),
                ):
                    if "CurrencyCode" in item:
                        currency = item.get("CurrencyCode", None)
                if currency is None:
                    continue

                shipping_time = item_offer.get("ShippingTime", d)
                shipping_time_min = int(
                    shipping_time.get("minimumHours", 0) / 24
                )
                shipping_time_max = int(
                    shipping_time.get("maximumHours", 0) / 24
                )
                availability_type = shipping_time.get("availabilityType", None)

                seller_feedback_rating = item_offer.get(
                    "SellerFeedbackRating", d
                )
                rating = {
                    "min": seller_feedback_rating.get(
                        "SellerPositiveFeedbackRating", 0
                    ),
                    "max": seller_feedback_rating.get(
                        "SellerPositiveFeedbackRating", 0
                    ),
                }
                feedback = seller_feedback_rating.get("FeedbackCount", 0)

                ships_from = (
                    item_offer.get("ShipsFrom", d)
                    .get("Country", country)
                    .lower()
                )
                if ships_from == "gb":
                    ships_from = "uk"
                domestic = ships_from == country.lower()

                prime_information = {
                    "is_prime": item_offer.get("PrimeInformation", d).get(
                        "IsPrime", False
                    ),
                    "is_national_prime": item_offer.get(
                        "PrimeInformation", d
                    ).get("IsNationalPrime", False),
                }

                offers.append(
                    {
                        "asin": asin,
                        "country": country,
                        "condition": condition,
                        "subcondition": subcondition,
                        "currency": currency,
                        "product_price": product_price,
                        "shipping_price": shipping_price,
                        "price": landed_price,
                        "shipping_time": {
                            "min": shipping_time_min,
                            "max": shipping_time_max,
                            "availability_type": availability_type,
                        },
                        "rating": rating,
                        "feedback": feedback,
                        "domestic": domestic,
                        "ships_from": ships_from,
                        "fba": item_offer.get("IsFulfilledByAmazon", False),
                        "is_buybox_winner": item_offer.get(
                            "IsBuyBoxWinner", False
                        ),
                        "seller_id": item_offer.get("SellerId", None),
                        "is_featured_merchant": item_offer.get(
                            "IsFeaturedMerchant", False
                        ),
                        "prime_information": prime_information,
                        "condition_notes": item_offer.get(
                            "ConditionNotes", ""
                        ),
                        "type": "SpItemOffer",
                    }
                )
            result[asin] = {
                "asin": asin,
                "offers": offers,
                "summary": "",
                "time": cur_time,
            }
        return result
