"""Shared Calculator automation utilities.

This module provides the CalculatorInteractor class for opening the Windows
Calculator app, typing expressions, and capturing results using pywinauto.
It is used by the RPA Core skills in the skills/ directory.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import logging
import subprocess
import pywinauto
from pywinauto import timings
import time

logger = logging.getLogger(__name__)

DEFAULT_CALCULATOR_PATH = r"C:\Windows\System32\calc.exe"


@dataclass
class CalculatorResult:
    """Result of a single test expression."""

    expression: str
    expected: str
    actual: Optional[str]
    passed: bool

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"CalculatorResult(expression='{self.expression}', status={status})"


class CalculatorInteractor:
    """Interact with Windows Calculator application."""

    def __init__(self, calculator_path: Optional[str] = None):
        self.calculator_path: Optional[str] = calculator_path
        self.app: Optional[pywinauto.Application] = None
        self.window = None

    def launch(self) -> bool:
        """Launch the Calculator application.

        Returns:
            True if calculator launched successfully, False otherwise.
        """
        path = self.calculator_path or DEFAULT_CALCULATOR_PATH

        if not Path(path).is_file():
            logger.error("Calculator executable not found: %s", path)
            return False

        max_retries = 2
        base_delay = 0.5
        self._cleanup_orphaned_calculators()

        for attempt in range(max_retries):
            try:
                self.app = pywinauto.Application(backend="uia").start(path)
                found = self._find_calculator_window(timeout=15)
                self.window = self.app.window(handle=found.handle)
                return True
            except (
                pywinauto.timings.TimeoutError,
                pywinauto.findwindows.ElementNotFoundError,
                pywinauto.base_wrapper.ElementNotEnabled,
                AttributeError,
                OSError,
                RuntimeError,
            ) as e:
                self.close()
                self._cleanup_orphaned_calculators()
                if attempt == max_retries - 1:
                    logger.error("Failed to launch calculator after %s attempts: %s", max_retries, e)
                    return False
                delay = base_delay * (2 ** attempt)
                logger.warning("Attempt %s failed: %s. Retrying in %.1fs...", attempt + 1, e, delay)
                time.sleep(delay)

        return False

    def ensure_visible(self) -> None:
        """Ensure the calculator window is visible and focused."""
        if not self.app:
            raise RuntimeError("Calculator not launched")
        window = self._window()
        window.set_focus()
        window.maximize()

    def type_expression(self, expression: str) -> str:
        """Type an expression into the calculator.

        Args:
            expression: The arithmetic expression to type.

        Returns:
            The expression that was typed.
        """
        if not self.app:
            raise RuntimeError("Calculator not launched")

        self.ensure_visible()
        window = self._window()

        window.type_keys("{ESC}", pause=0.05)
        timings.wait_until_passes(10, 0.25, lambda: window.wait("ready", timeout=1))
        window.type_keys(expression, with_spaces=True, pause=0.03)
        window.type_keys("{ENTER}", pause=0.05)

        return expression

    def get_result(self) -> Optional[str]:
        """Get the current result displayed in the calculator.

        Returns:
            The result string, or None if no result is available.

        Raises:
            RuntimeError: If the calculator has not been launched.
        """
        if not self.app:
            raise RuntimeError("Calculator not launched")

        try:
            display = self._window().child_window(
                auto_id="CalculatorResults", control_type="Text"
            )
            value = display.window_text()
            return self._normalize_result(value)
        except Exception as e:
            logger.warning("Failed to read calculator result: %s", e)
            return None

    def close(self) -> None:
        """Close the Calculator application (best-effort cleanup).

        Uses Application.kill() via the class because pywinauto's
        __getattribute__ intercepts direct attribute access and tries
        to resolve it as a window spec.
        """
        if self.app:
            try:
                pywinauto.Application.kill(self.app)
            except Exception as e:
                logger.warning("Calculator could not be closed cleanly: %s", e)
                close = getattr(self.app, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception as close_error:
                        logger.warning("Calculator close fallback failed: %s", close_error)
            finally:
                self.app = None
                self.window = None
        self._cleanup_orphaned_calculators()

    def _window(self):
        """Return the Calculator top-level window."""
        if not self.app:
            raise RuntimeError("Calculator not launched")
        if self.window is not None:
            return self.window
        found = self._find_calculator_window(timeout=5)
        self.window = self.app.window(handle=found.handle)
        return self.window

    def _find_calculator_window(self, timeout: float):
        """Find Calculator by stable UIA controls instead of localized title text."""
        deadline = time.monotonic() + timeout
        desktop = pywinauto.Desktop(backend="uia")

        while time.monotonic() < deadline:
            for window in desktop.windows():
                if self._looks_like_calculator(window):
                    return window
            time.sleep(0.25)

        raise pywinauto.timings.TimeoutError("Timed out waiting for Calculator window")

    @staticmethod
    def _looks_like_calculator(window) -> bool:
        try:
            title = window.window_text()
            if "calculator" in title.lower():
                return True
        except Exception:
            pass

        try:
            return window.child_window(auto_id="CalculatorResults", control_type="Text").exists(timeout=0)
        except Exception:
            return False

    @staticmethod
    def _cleanup_orphaned_calculators() -> None:
        """Best-effort cleanup for orphaned Calculator processes (both classic and UWP)."""
        for image in ("calc.exe", "CalculatorApp.exe"):
            for _attempt in range(4):
                try:
                    subprocess.run(
                        ["taskkill", "/IM", image, "/F"],
                        capture_output=True,
                        check=False,
                        text=True,
                    )
                except OSError as exc:
                    logger.debug("Unable to run %s cleanup: %s", image, exc)
                    break
                time.sleep(0.25)

    @staticmethod
    def _normalize_result(value: Optional[str]) -> Optional[str]:
        """Convert Calculator's display text to the comparable result value."""
        if not value:
            return None

        normalized = value.strip()
        if normalized.startswith("Display is"):
            normalized = normalized[len("Display is"):].strip()

        return normalized or None
