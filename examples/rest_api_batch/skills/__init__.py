from __future__ import annotations

"""Shared constants and helpers for the REST API Batch Processor skills."""

from collections.abc import Callable
from typing import NoReturn

import requests

from rpacore import BusinessException, SystemException

API_MODE_FIXTURE = "fixture"
API_MODE_LIVE = "live"
API_MODES = {API_MODE_FIXTURE, API_MODE_LIVE}
HTTP_TIMEOUT_SECONDS = 30


def fetch_json(
    url: str,
    *,
    action: str,
    resource: str,
    request_get: Callable[..., requests.Response] = requests.get,
) -> object:
    """Fetch and decode one JSON response with consistent retry semantics."""
    try:
        response = request_get(url, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except ValueError as exc:
        raise SystemException(
            f"Invalid JSON in {resource} response: {exc}",
            action=action,
        ) from exc
    except requests.exceptions.HTTPError as exc:
        raise_http_error(exc, action=action, resource=resource)
    except requests.exceptions.ConnectionError as exc:
        raise SystemException(
            f"Connection error fetching {resource}: {exc}",
            action=action,
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise SystemException(
            f"Timeout fetching {resource}: {exc}",
            action=action,
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise SystemException(
            f"Error fetching {resource}: {exc}",
            action=action,
        ) from exc


def raise_http_error(
    exc: requests.exceptions.HTTPError,
    *,
    action: str,
    resource: str,
) -> NoReturn:
    """Classify permanent client responses separately from retryable failures."""
    status_code = exc.response.status_code if exc.response is not None else None
    raw_reason = exc.response.reason if exc.response is not None else str(exc)
    reason = " ".join(str(raw_reason).split())[:200] or "Unknown reason"
    if (
        status_code is not None
        and 400 <= status_code < 500
        and status_code not in {408, 429}
    ):
        raise BusinessException(
            f"{resource} request was rejected: {status_code} — {reason}",
            action=action,
            stop=True,
        ) from exc
    raise SystemException(
        f"HTTP error fetching {resource}: {status_code} — {reason}",
        action=action,
    ) from exc
