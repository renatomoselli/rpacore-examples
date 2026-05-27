"""Tests for Calculator interactor module."""
import pytest
from unittest.mock import Mock
from calculator_calculator import CalculatorInteractor


class TestCalculatorInteractor:
    """Test suite for CalculatorInteractor."""
    
    def test_init_default_path(self):
        """Test initialization with default calculator path."""
        interactor = CalculatorInteractor()
        assert interactor.calculator_path is None
        assert interactor.app is None
    
    def test_init_custom_path(self):
        """Test initialization with custom calculator path."""
        custom_path = r"C:\MyCalculator\calc.exe"
        interactor = CalculatorInteractor()
        interactor.calculator_path = custom_path
        assert interactor.calculator_path == custom_path
    
    def test_launch_returns_false_when_start_fails(self, monkeypatch):
        """Test launch returns False when pywinauto cannot start Calculator."""
        interactor = CalculatorInteractor()
        monkeypatch.setattr("calculator_calculator.time.sleep", lambda delay: None)

        class FailingApplication:
            def __init__(self, backend=None):
                pass

            def start(self, path):
                raise RuntimeError("start failed")

        monkeypatch.setattr("calculator_calculator.pywinauto.Application", FailingApplication)

        assert interactor.launch() is False
        assert interactor.app is None
    
    def test_ensure_visible_raises_when_not_launched(self):
        """Test ensure_visible raises when calculator not launched."""
        interactor = CalculatorInteractor()
        with pytest.raises(RuntimeError, match="Calculator not launched"):
            interactor.ensure_visible()
    
    def test_type_expression_raises_when_not_launched(self):
        """Test type_expression raises when calculator not launched."""
        interactor = CalculatorInteractor()
        with pytest.raises(RuntimeError, match="Calculator not launched"):
            interactor.type_expression("2+2")
    
    def test_get_result_returns_none_when_not_launched(self):
        """Test get_result returns None when calculator not launched."""
        interactor = CalculatorInteractor()
        result = interactor.get_result()
        assert result is None
    
    def test_close_cleans_up(self):
        """Test close cleans up app reference."""
        interactor = CalculatorInteractor()
        app = Mock()
        interactor.app = app

        interactor.close()

        app.close.assert_called_once_with()
        assert interactor.app is None

    def test_normalize_result_strips_calculator_prefix(self):
        """Test Calculator display text is normalized for comparison."""
        assert CalculatorInteractor._normalize_result("Display is 4") == "4"
