"""Tests for CSV loader module."""
from __future__ import annotations

from calculator_csv_loader import (
    validate_csv_file,
    load_csv_expressions,
    save_results,
)
import tempfile
import os

import pytest

import calculator_csv_loader


def test_validate_csv_file_missing_file(tmp_path):
    """Test validate_csv_file with missing file."""
    result = validate_csv_file(str(tmp_path / "nonexistent.csv"))
    assert result is False


def test_validate_csv_file_wrong_columns():
    """Test validate_csv_file with wrong columns."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write('wrong,columns\n1,2\n')
        temp_path = f.name
    
    try:
        result = validate_csv_file(temp_path)
        assert result is False
    finally:
        os.unlink(temp_path)


def test_validate_csv_file_valid():
    """Test validate_csv_file with valid columns."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write('expression,expected_result\n2+2,4\n')
        temp_path = f.name
    
    try:
        result = validate_csv_file(temp_path)
        assert result is True
    finally:
        os.unlink(temp_path)


def test_load_csv_expressions():
    """Test load_csv_expressions with valid file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write('expression,expected_result\n2+2,4\n')
        temp_path = f.name
    
    try:
        expressions = load_csv_expressions(temp_path)
        assert len(expressions) == 1
        assert expressions[0]['expression'] == '2+2'
        assert expressions[0]['expected_result'] == '4'
    finally:
        os.unlink(temp_path)


def test_load_csv_expressions_empty_expression():
    """Test load_csv_expressions with empty expression."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write('expression,expected_result\n\n\n')
        temp_path = f.name
    
    try:
        expressions = load_csv_expressions(temp_path)
        assert len(expressions) == 0
    finally:
        os.unlink(temp_path)


def test_load_csv_expressions_quotes():
    """Test load_csv_expressions with quoted values."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write('expression,expected_result\n"2+2",4\n')
        temp_path = f.name
    
    try:
        expressions = load_csv_expressions(temp_path)
        assert len(expressions) == 1
        assert expressions[0]['expression'] == '2+2'
    finally:
        os.unlink(temp_path)


def test_load_csv_expressions_missing_trailing_value(tmp_path):
    csv_file = tmp_path / "short-row.csv"
    csv_file.write_text("expression,expected_result\n2+2\n", encoding="utf-8")

    expressions = load_csv_expressions(str(csv_file))

    assert expressions[0]["expected_result"] == ""


def test_save_results():
    """Test save_results saves to CSV."""
    results = [
        {'expression': '2+2', 'expected_result': '4', 'actual': '4', 'passed': True},
    ]
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        temp_path = f.name
    
    try:
        save_results(results, temp_path)
        
        with open(temp_path, 'r') as f:
            content = f.read()
        
        assert 'expression' in content
        assert 'passed' in content
        assert '2+2' in content
        assert 'expected_result' in content
    finally:
        os.unlink(temp_path)


def test_save_results_preserves_existing_file_when_publish_fails(tmp_path, monkeypatch):
    output = tmp_path / "results.csv"
    output.write_text("previous\n", encoding="utf-8")
    monkeypatch.setattr(
        calculator_csv_loader.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        save_results(
            [{"expression": "2+2", "expected_result": "4", "actual": "4", "passed": True}],
            str(output),
        )

    assert output.read_text(encoding="utf-8") == "previous\n"
    assert list(tmp_path.glob("*.tmp")) == []


def test_load_csv_expressions_missing_file(tmp_path):
    """Test load_csv_expressions raises ValueError for missing file."""
    import pytest
    with pytest.raises(ValueError, match="Unable to open CSV file"):
        load_csv_expressions(str(tmp_path / "nonexistent.csv"))


def test_load_csv_expressions_missing_columns():
    """Test load_csv_expressions raises ValueError for missing columns."""
    import pytest
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write('wrong,columns\n1,2\n')
        temp_path = f.name
    
    try:
        with pytest.raises(ValueError, match="Missing required columns"):
            load_csv_expressions(temp_path)
    finally:
        os.unlink(temp_path)
