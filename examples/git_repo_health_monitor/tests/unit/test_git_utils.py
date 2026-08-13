from __future__ import annotations

from datetime import datetime, timezone

import pytest

from steps.git_utils import parse_git_datetime


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-06-18T12:00:00+0000", datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)),
        ("2026-06-18T12:00:00+00:00", datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)),
        ("2026-06-18T09:00:00-0300", datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)),
        ("2026-06-18T12:00:00", datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)),
    ],
)
def test_parse_git_datetime_normalizes_to_utc(value, expected):
    assert parse_git_datetime(value) == expected


@pytest.mark.parametrize("value", ["", "bad", "2026-06-18T12:00:00+0"])
def test_parse_git_datetime_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_git_datetime(value)
