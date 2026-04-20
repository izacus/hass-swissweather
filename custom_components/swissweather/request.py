"""Shared MeteoSwiss request helpers with targeted retries."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
from typing import TypeVar

from aiohttp import ClientConnectionError, ClientResponseError, ClientSession

REQUEST_TIMEOUT = 10
_RETRY_DELAYS = (0.25, 0.75)
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

_T = TypeVar("_T")


def is_transient_request_error(err: BaseException) -> bool:
    """Return True when a request failure is worth retrying."""
    if isinstance(err, TimeoutError):
        return True
    if isinstance(err, ClientResponseError):
        return err.status in _RETRYABLE_STATUS_CODES
    return isinstance(err, ClientConnectionError)


async def async_get_with_retry(
    session: ClientSession,
    url: str,
    *,
    logger: logging.Logger,
    response_handler: Callable[[object], Awaitable[_T]],
    **request_kwargs,
) -> _T:
    """Run a GET request and retry only on transient transport failures."""
    max_attempts = len(_RETRY_DELAYS) + 1
    for attempt in range(1, max_attempts + 1):
        try:
            async with session.get(url, **request_kwargs) as response:
                response.raise_for_status()
                return await response_handler(response)
        except Exception as err:
            if not is_transient_request_error(err) or attempt >= max_attempts:
                raise
            logger.debug(
                "Transient MeteoSwiss request failure for %s on attempt %d/%d; retrying",
                url,
                attempt,
                max_attempts,
                exc_info=err,
            )
            await asyncio.sleep(_RETRY_DELAYS[attempt - 1])

    raise RuntimeError("Request retry loop exited unexpectedly")
