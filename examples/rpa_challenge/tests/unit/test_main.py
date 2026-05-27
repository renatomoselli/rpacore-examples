"""Unit tests for main.py helpers."""

from unittest.mock import Mock

from main import _stop_playwright


def test_stop_playwright_stops_and_removes_runtime_handle():
    pw = Mock()
    shared_data = {"_pw": pw}

    _stop_playwright(shared_data)

    pw.stop.assert_called_once()
    assert "_pw" not in shared_data


def test_stop_playwright_is_idempotent():
    shared_data = {}

    _stop_playwright(shared_data)

    assert shared_data == {}
