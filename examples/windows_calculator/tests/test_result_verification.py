"""Tests for result verification module."""
from __future__ import annotations

from calculator_utils import CalculatorResult
from calculator_test_runner import (
    CalculatorTestRunner,
)
import tempfile
import os
from unittest.mock import Mock


def test_calculatorresult_repr_pass():
    """Test CalculatorResult repr for passed test."""
    result = CalculatorResult("2+2", "4", "4", True)
    assert "PASS" in repr(result)
    assert "2+2" in repr(result)


def test_calculatorresult_repr_fail():
    """Test CalculatorResult repr for failed test."""
    result = CalculatorResult("5*3", "15", "10", False)
    assert "FAIL" in repr(result)
    assert "5*3" in repr(result)


def test_calculatorresult_equality():
    """Test CalculatorResult compares by value."""
    assert CalculatorResult("2+2", "4", "4", True) == CalculatorResult("2+2", "4", "4", True)


def test_calculatortestrunner_init_default():
    """Test CalculatorTestRunner initialization with default calculator path."""
    runner = CalculatorTestRunner()
    assert runner.results == []


def test_calculatortestrunner_init_custom_path():
    """Test CalculatorTestRunner initialization with custom calculator path."""
    runner = CalculatorTestRunner(calculator_path="custom/calculator.exe")
    # Note: we can't easily assert the interactor's calculator_path
    # but the initialization succeeds
    # The calculator_path is set on the interactor via centralized approach
    assert runner.interactor.calculator_path == "custom/calculator.exe"


def test_calculatortestrunner_run_tests_empty():
    """Test run_tests with empty expression list."""
    runner = CalculatorTestRunner()
    results = runner.run_tests([])
    assert results == []


def test_calculatortestrunner_run_tests_no_launch():
    """Test run_tests when calculator launch fails."""
    runner = CalculatorTestRunner()
    runner.interactor.launch = lambda: False
    runner.interactor.close = Mock()
    
    expressions = [{"expression": "2+2", "expected_result": "4"}]
    results = runner.run_tests(expressions)
    
    assert len(results) == 0
    runner.interactor.close.assert_called_once_with()


def test_calculatortestrunner_run_tests_fail_fast():
    """Test fail-fast stops on the first failed result."""
    runner = CalculatorTestRunner()
    runner.interactor.launch = lambda: True
    runner.interactor.type_expression = lambda expr: expr
    runner.interactor.get_result = lambda: "wrong"
    runner.interactor.close = lambda: None
    
    expressions = [
        {"expression": "2+2", "expected_result": "4"},
        {"expression": "3+3", "expected_result": "6"}
    ]
    results = runner.run_tests(expressions, fail_fast=True)
    
    assert len(results) == 1


def test_calculatortestrunner_run_tests_result_missing():
    """Test run_tests records a failure when no result is returned."""
    runner = CalculatorTestRunner()
    
    # Mock the interactor methods
    runner.interactor.launch = lambda: True
    runner.interactor.type_expression = lambda expr: expr
    runner.interactor.get_result = lambda: None
    runner.interactor.close = lambda: None
    
    expressions = [{"expression": "2+2", "expected_result": "4"}]
    results = runner.run_tests(expressions, fail_fast=False)
    
    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].actual is None


def test_calculatortestrunner_run_tests_result_match():
    """Test run_tests records a pass when actual matches expected."""
    runner = CalculatorTestRunner()
    
    # Mock the interactor methods
    runner.interactor.launch = lambda: True
    runner.interactor.type_expression = lambda expr: expr
    runner.interactor.get_result = lambda: "4"
    runner.interactor.close = lambda: None
    
    expressions = [{"expression": "2+2", "expected_result": "4"}]
    results = runner.run_tests(expressions, fail_fast=False)
    
    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].actual == "4"


def test_calculatortestrunner_run_tests_type_expression_raises():
    """Test run_tests records failure when type_expression raises."""
    runner = CalculatorTestRunner()
    runner.interactor.launch = lambda: True
    def raise_error(expr):
        raise RuntimeError("typing failed")
    runner.interactor.type_expression = raise_error
    runner.interactor.close = lambda: None
    
    expressions = [{"expression": "2+2", "expected_result": "4"}]
    results = runner.run_tests(expressions)
    
    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].actual is None


def test_calculatortestrunner_run_tests_exception_records_failure():
    """Test run_tests records exceptions as failures."""
    runner = CalculatorTestRunner()
    runner.interactor.launch = lambda: True

    def raise_error(expr):
        raise RuntimeError("typing failed")

    runner.interactor.type_expression = raise_error
    runner.interactor.close = lambda: None

    expressions = [{"expression": "2+2", "expected_result": "4"}]
    results = runner.run_tests(expressions)

    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].actual is None


def test_calculatortestrunner_get_report_empty():
    """Test get_report with no results."""
    runner = CalculatorTestRunner()
    report = runner.get_report()
    assert "No tests run yet." in report


def test_calculatortestrunner_get_report_with_results():
    """Test get_report with results."""
    runner = CalculatorTestRunner()
    runner.interactor.launch = lambda: True
    runner.interactor.type_expression = lambda expr: expr
    results = iter(["4", "10"])
    runner.interactor.get_result = lambda: next(results)
    runner.interactor.close = lambda: None

    runner.run_tests([
        {"expression": "2+2", "expected_result": "4"},
        {"expression": "5*3", "expected_result": "15"},
    ])
    
    report = runner.get_report()
    
    assert "Total:" in report
    assert "PASS" in report
    assert "FAIL" in report
    assert "2+2" in report
    assert "5*3" in report


def test_calculatortestrunner_save_report():
    """Test save_report saves to CSV."""
    runner = CalculatorTestRunner()
    runner.interactor.launch = lambda: True
    runner.interactor.type_expression = lambda expr: expr
    runner.interactor.get_result = lambda: "4"
    runner.interactor.close = lambda: None

    runner.run_tests([{"expression": "2+2", "expected_result": "4"}])
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        temp_path = f.name
    
    try:
        runner.save_report(temp_path)
        
        with open(temp_path, 'r') as f:
            content = f.read()
        
        assert 'expression' in content
        assert 'passed' in content
        assert '2+2' in content
    finally:
        os.unlink(temp_path)


def test_calculatortestrunner_run_tests_get_result_raises():
    """Test run_tests records failure when get_result raises."""
    runner = CalculatorTestRunner()
    runner.interactor.launch = lambda: True
    runner.interactor.type_expression = lambda expr: expr

    def raise_error():
        raise RuntimeError("reading failed")

    runner.interactor.get_result = raise_error
    runner.interactor.close = lambda: None

    expressions = [{"expression": "2+2", "expected_result": "4"}]
    results = runner.run_tests(expressions)

    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].actual is None
