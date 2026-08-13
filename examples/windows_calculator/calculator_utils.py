"""Shared Calculator automation utilities.

This module provides the CalculatorInteractor class for opening the Windows
Calculator app, typing expressions, and capturing results using pywinauto.
It is used by the RPA Core steps in the steps/ directory.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional

import logging
import subprocess
import time

logger = logging.getLogger(__name__)

CALCULATOR_BUTTON_IDS = {
    "0": "num0Button",
    "1": "num1Button",
    "2": "num2Button",
    "3": "num3Button",
    "4": "num4Button",
    "5": "num5Button",
    "6": "num6Button",
    "7": "num7Button",
    "8": "num8Button",
    "9": "num9Button",
    "+": "plusButton",
    "-": "minusButton",
    "*": "multiplyButton",
    "/": "divideButton",
    ".": "decimalSeparatorButton",
    "(": "openParenthesisButton",
    ")": "closeParenthesisButton",
}

# Lazy import: CalculatorResult can be imported without pywinauto,
# but CalculatorInteractor methods require it at call time.
# The try/except keeps calculator_utils.pywinauto as a module attribute
# even when pywinauto is not installed, preserving existing test monkeypatches.
try:
    import pywinauto
    from pywinauto import timings
except ImportError:
    pywinauto = None  # type: ignore[assignment]
    timings = None  # type: ignore[assignment]


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
        self.app = None
        self.window = None
        self.process_id: int | None = None

    def launch(self) -> bool:
        """Launch the Calculator application.

        Returns:
            True if calculator launched successfully, False otherwise.
        """
        if pywinauto is None:
            logger.error("pywinauto is not available \u2014 cannot launch Calculator")
            return False

        path = self.calculator_path or self._default_calculator_path()

        if path is None or not Path(path).is_file():
            logger.error("Calculator executable not found: %s", path)
            return False

        max_retries = 2
        base_delay = 0.5
        existing_handles = self._calculator_window_handles()

        for attempt in range(max_retries):
            try:
                self.app = pywinauto.Application(backend="uia").start(path)
                app_process = getattr(self.app, "process", None)
                if app_process is not None:
                    self.process_id = int(app_process)
                found = self._find_calculator_window(
                    timeout=15,
                    excluded_handles=existing_handles,
                )
                self.window = self.app.window(handle=found.handle)
                window_process = getattr(found, "process_id", None)
                if callable(window_process):
                    self.process_id = int(window_process())
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
        """Type an expression into the calculator."""
        if not self.app:
            raise RuntimeError("Calculator not launched")
        if pywinauto is None:
            raise RuntimeError("pywinauto is not available")

        self.ensure_visible()
        window = self._window()

        self._click_button(window, "clearButton")
        timings.wait_until_passes(10, 0.25, lambda: window.wait("ready", timeout=1))
        for char in expression:
            if char.isspace():
                continue
            button_id = self._button_id_for_char(char)
            self._click_button(window, button_id)
        self._click_button(window, "equalButton")
        timings.wait_until_passes(10, 0.25, lambda: window.wait("ready", timeout=1))

        return expression

    def get_result(self) -> Optional[str]:
        """Get the current result displayed in the calculator."""
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
        """Close the Calculator application (best-effort cleanup)."""
        process_id = self.process_id
        if self.app:
            if pywinauto is not None:
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
            else:
                logger.warning("pywinauto not available \u2014 cannot kill Calculator process")
                close = getattr(self.app, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception as close_error:
                        logger.warning("Calculator close fallback failed: %s", close_error)
            self.app = None
            self.window = None
        self.process_id = None
        if process_id is not None:
            self._terminate_process(process_id)

    def _window(self):
        """Return the Calculator top-level window."""
        if pywinauto is None:
            raise RuntimeError("pywinauto is not available")

        if not self.app:
            raise RuntimeError("Calculator not launched")
        if self.window is not None:
            return self.window
        found = self._find_calculator_window(timeout=5, process_id=self.process_id)
        self.window = self.app.window(handle=found.handle)
        return self.window

    def _find_calculator_window(
        self,
        timeout: float,
        *,
        excluded_handles: set[int] | None = None,
        process_id: int | None = None,
    ):
        """Find Calculator by stable UIA controls instead of localized title text."""
        if pywinauto is None:
            raise RuntimeError("pywinauto is not available")

        deadline = time.monotonic() + timeout
        desktop = pywinauto.Desktop(backend="uia")

        while time.monotonic() < deadline:
            for window in desktop.windows():
                if excluded_handles and getattr(window, "handle", None) in excluded_handles:
                    continue
                window_process = getattr(window, "process_id", None)
                if process_id is not None and (
                    not callable(window_process) or int(window_process()) != process_id
                ):
                    continue
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
    def _button_id_for_char(char: str) -> str:
        try:
            return CALCULATOR_BUTTON_IDS[char]
        except KeyError as exc:
            raise RuntimeError(f"Unsupported calculator input character: {char!r}") from exc

    @staticmethod
    def _click_button(window, auto_id: str) -> None:
        button = window.child_window(auto_id=auto_id, control_type="Button")
        timings.wait_until_passes(5, 0.1, lambda: button.wait("enabled", timeout=1))
        button.click_input()

    @staticmethod
    def _default_calculator_path() -> str | None:
        windows_dir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
        if not windows_dir:
            return None
        return str(Path(windows_dir) / "System32" / "calc.exe")

    @classmethod
    def _calculator_window_handles(cls) -> set[int]:
        """Return Calculator windows that existed before this launch attempt."""
        if pywinauto is None:
            return set()
        try:
            return {
                int(window.handle)
                for window in pywinauto.Desktop(backend="uia").windows()
                if cls._looks_like_calculator(window)
            }
        except Exception as exc:
            logger.debug("Unable to enumerate existing Calculator windows: %s", exc)
            return set()

    @staticmethod
    def _terminate_process(process_id: int) -> None:
        """Best-effort cleanup limited to the Calculator process this instance owns."""
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process_id), "/T", "/F"],
                capture_output=True,
                check=False,
                text=True,
            )
        except OSError as exc:
            logger.debug("Unable to clean up Calculator PID %s: %s", process_id, exc)

    @staticmethod
    def _normalize_result(value: Optional[str]) -> Optional[str]:
        """Convert Calculator's display text to the comparable result value."""
        if not value:
            return None

        normalized = value.strip()
        if normalized.startswith("Display is"):
            normalized = normalized[len("Display is"):].strip()

        return normalized or None
