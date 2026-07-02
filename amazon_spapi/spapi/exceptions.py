# -*- coding: utf-8
"""SP-API exception types and retry groups."""

from sp_api.base.exceptions import (
    SellingApiBadRequestException,
    SellingApiForbiddenException,
    SellingApiNotFoundException,
    SellingApiRequestThrottledException,
    SellingApiServerException,
    SellingApiStateConflictException,
    SellingApiTemporarilyUnavailableException,
    SellingApiTooLargeException,
    SellingApiUnsupportedFormatException,
)


class SellingApiInvalidAsinException(SellingApiBadRequestException):
    pass


exceptions_to_retry = (
    SellingApiRequestThrottledException,
    SellingApiServerException,
    SellingApiTemporarilyUnavailableException,
    SellingApiStateConflictException,
)
exceptions_not_retry = (
    SellingApiNotFoundException,
    SellingApiForbiddenException,
    SellingApiTooLargeException,
    SellingApiUnsupportedFormatException,
)
