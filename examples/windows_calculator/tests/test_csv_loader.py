"""Tests for CSV loader module."""
from calculator_csv_loader import (
    validate_csv_file,
    load_csv_expressions,
    save_results,
)
import tempfile
import os


def test_validate_csv_file_missing_file():
    """Test validate_csv_file with missing file."""
    result = validate_csv_file("/nonexistent.csv")
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


def test_save_results():
    """Test save_results saves to CSV."""
    results = [
        {'expression': '2+2', 'expected': '4', 'actual': '4', 'passed': True},
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
    finally:
        os.unlink(temp_path)
