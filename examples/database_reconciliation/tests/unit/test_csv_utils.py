from __future__ import annotations

import pytest
from rpacore import SystemException

from steps._csv_utils import read_csv


def test_read_csv_returns_rows_for_valid_schema(tmp_path):
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("id,name\n1,Ada\n", encoding="utf-8")

    rows = read_csv(csv_path, ("id", "name"), action="test")

    assert rows == [{"id": "1", "name": "Ada"}]


def test_read_csv_rejects_missing_required_headers(tmp_path):
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("id\n1\n", encoding="utf-8")

    with pytest.raises(SystemException, match="missing required header"):
        read_csv(csv_path, ("id", "name"), action="test")


def test_read_csv_wraps_io_errors(tmp_path):
    missing_path = tmp_path / "missing.csv"

    with pytest.raises(SystemException, match="Unable to read CSV file"):
        read_csv(missing_path, ("id",), action="test")
