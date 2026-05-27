"""Calculator automation module.

This module provides the CalculatorInteractor class for opening the Windows
Calculator app, typing expressions, and capturing results using pywinauto.
"""
from typing import Optional
import logging
import pywinauto
from pywinauto import timings
import time

logger = logging.getLogger(__name__)


class CalculatorInteractor:
    """Interact with Windows Calculator application."""
    
    def __init__(self):
        """Initialize the Calculator interactor.
        
        Args:
            calculator_path: Optional path to calculator executable.
                If None, uses system default. (Passed via centralized approach)
        """
        self.calculator_path: Optional[str] = None
        self.app: Optional[pywinauto.Application] = None
    
    def launch(self) -> bool:
        """Launch the Calculator application.
        
        Returns:
            True if calculator launched successfully, False otherwise.
        """
        path = self.calculator_path or r"C:\Windows\System32\calc.exe"
        
        # Retry logic with exponential backoff
        max_retries = 5
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                self.app = pywinauto.Application(backend="uia").start(path)
                self._window().wait("ready", timeout=30)
                return True
            except Exception as e:
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
        
        # Bring to front and focus
        window = self._window()
        window.set_focus()
        window.maximize()
    
    def type_expression(self, expression: str) -> str:
        """Type an expression into the calculator.
        
        Args:
            expression: The arithmetic expression to type.
                Supports digits, operators (+, -, *, /, =, parentheses).
                The expression is intentionally passed through to Calculator.
        
        Returns:
            The expression that was typed.
        """
        if not self.app:
            raise RuntimeError("Calculator not launched")
        
        self.ensure_visible()
        window = self._window()

        # Escape clears the current Calculator entry without relying on a private edit control.
        window.type_keys("{ESC}", pause=0.05)
        timings.wait_until_passes(10, 0.25, lambda: window.wait("ready", timeout=1))
        window.type_keys(expression, with_spaces=True, pause=0.03)
        window.type_keys("{ENTER}", pause=0.05)
        
        return expression
    
    def get_result(self) -> Optional[str]:
        """Get the current result displayed in the calculator.
        
        Returns:
            The result string, or None if calculator is not ready.
        """
        if not self.app:
            return None
        
        try:
            display = self._window().child_window(auto_id="CalculatorResults", control_type="Text")
            value = display.window_text()
            return self._normalize_result(value)
        except Exception as e:
            logger.warning("Failed to read calculator result: %s", e)
            return None
    
    def close(self) -> None:
        """Close the Calculator application."""
        if self.app:
            try:
                self.app.close()
            except pywinauto.findwindows.ElementNotFoundError as e:
                logger.warning("Calculator window was already closed: %s", e)
            except pywinauto.base_wrapper.ElementNotEnabled as e:
                logger.warning("Calculator window could not be closed cleanly: %s", e)
            finally:
                self.app = None

    def _window(self):
        """Return the Calculator top-level window."""
        if not self.app:
            raise RuntimeError("Calculator not launched")
        return self.app.window(title_re=".*Calculator.*")

    @staticmethod
    def _normalize_result(value: Optional[str]) -> Optional[str]:
        """Convert Calculator's display text to the comparable result value."""
        if not value:
            return None

        normalized = value.strip()
        prefixes = ("Display is", "Display is ")
        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):].strip()
                break

        return normalized or None


def main():
    """Simple test of the Calculator interactor."""
    interactor = CalculatorInteractor()
    
    if interactor.launch():
        print("Calculator launched successfully!")
        
        # Test a simple expression
        interactor.type_expression("2 + 2")
        result = interactor.get_result()
        print(f"Result: {result}")
        
        interactor.close()
    else:
        print("Failed to launch calculator")


if __name__ == "__main__":
    main()
