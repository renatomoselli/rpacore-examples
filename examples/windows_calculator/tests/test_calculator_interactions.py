"""Tests for Calculator interactor module."""
from types import SimpleNamespace

import pytest
from unittest.mock import Mock

import calculator_utils
from calculator_utils import CalculatorInteractor

pytestmark = pytest.mark.windows


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
        monkeypatch.setattr("calculator_utils.time.sleep", lambda delay: None)
        monkeypatch.setattr("calculator_utils.Path.is_file", lambda _path: True)

        class FailingApplication:
            def __init__(self, backend=None):
                pass

            def start(self, path):
                raise RuntimeError("start failed")

        fake_pywinauto = SimpleNamespace(
            Application=FailingApplication,
            timings=SimpleNamespace(TimeoutError=TimeoutError),
            findwindows=SimpleNamespace(ElementNotFoundError=RuntimeError),
            base_wrapper=SimpleNamespace(ElementNotEnabled=RuntimeError),
        )
        monkeypatch.setattr(calculator_utils, "pywinauto", fake_pywinauto)

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

    def test_get_result_raises_when_not_launched(self):
        """Test get_result raises when calculator not launched."""
        interactor = CalculatorInteractor()
        with pytest.raises(RuntimeError, match="Calculator not launched"):
            interactor.get_result()

    def test_close_cleans_up(self):
        """Test close cleans up app reference."""
        interactor = CalculatorInteractor()
        app = Mock()
        interactor.app = app

        interactor.close()

        app.close.assert_called_once_with()
        assert interactor.app is None
        assert interactor.window is None

    def test_normalize_result_strips_calculator_prefix(self):
        """Test Calculator display text is normalized for comparison."""
        assert CalculatorInteractor._normalize_result("Display is 4") == "4"

    def test_button_id_mapping_for_operators(self):
        """Test arithmetic operators map to Calculator button IDs."""
        assert CalculatorInteractor._button_id_for_char("+") == "plusButton"
        assert CalculatorInteractor._button_id_for_char("-") == "minusButton"
        assert CalculatorInteractor._button_id_for_char("*") == "multiplyButton"
        assert CalculatorInteractor._button_id_for_char("/") == "divideButton"
