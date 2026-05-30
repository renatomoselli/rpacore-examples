"""Backward-compatible shim — real implementation lives in calculator_utils.py."""

from calculator_utils import CalculatorInteractor, CalculatorResult  # noqa: F401

__all__ = ["CalculatorInteractor", "CalculatorResult"]
