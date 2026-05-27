"""Test runner for Windows Calculator batch expressions.

This module orchestrates the test execution, handles exceptions, and generates reports.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass
import logging
import sys

from calculator_csv_loader import load_csv_expressions, save_results, validate_csv_file
from calculator_calculator import CalculatorInteractor

logger = logging.getLogger(__name__)


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


class CalculatorTestRunner:
    """Orchestrate Calculator test execution."""

    def __init__(self, calculator_path: Optional[str] = None):
        """Initialize the test runner.

        Args:
            calculator_path: Optional path to calculator executable.
        """
        self.interactor = CalculatorInteractor()
        self.interactor.calculator_path = calculator_path
        self.results: List[CalculatorResult] = []

    def run_tests(self, expressions: List[Dict[str, Any]], fail_fast: bool = False) -> List[CalculatorResult]:
        """Run all tests from a list of expressions.

        Args:
            expressions: List of dictionaries with 'expression' and 'expected_result' keys.

        Returns:
            List of TestResult objects.
        """
        self.results = []

        if not expressions:
            logger.warning("No expressions to test")
            return []

        logger.info(f"Starting test run with {len(expressions)} expressions")

        # Launch calculator
        if not self.interactor.launch():
            logger.error("Failed to launch Calculator")
            self.interactor.close()
            return []

        try:
            for idx, expr_data in enumerate(expressions):
                try:
                    expression = expr_data['expression']
                    expected = expr_data['expected_result']

                    logger.info(f"Testing expression {idx + 1}/{len(expressions)}: {expression}")
                    logger.debug(f"Expression {idx + 1}: {expression}")

                    # Type the expression
                    self.interactor.type_expression(expression)

                    # Get the result
                    actual = self.interactor.get_result()

                    if actual is None:
                        logger.error(f"Expression {idx + 1}: Could not get result")
                        result = CalculatorResult(
                            expression=expression,
                            expected=expected,
                            actual=None,
                            passed=False
                        )
                    elif actual == expected:
                        logger.info(f"Expression {idx + 1}: PASS")
                        result = CalculatorResult(
                            expression=expression,
                            expected=expected,
                            actual=actual,
                            passed=True
                        )
                    else:
                        logger.error(f"Expression {idx + 1}: FAIL - Expected '{expected}', got '{actual}'")
                        result = CalculatorResult(
                            expression=expression,
                            expected=expected,
                            actual=actual,
                            passed=False
                        )

                    self.results.append(result)

                    # Fail-fast: stop on first failure
                    if fail_fast and not result.passed:
                        logger.info(f"Stopping after failure on expression {idx + 1}: {expression}")
                        break

                except Exception as e:
                    logger.error(f"Expression {idx + 1}: Exception: {e}")
                    logger.debug(f"Exception details: {type(e).__name__}: {str(e)}")
                    # Record failure but continue
                    result = CalculatorResult(
                        expression=expressions[idx]['expression'],
                        expected=expressions[idx]['expected_result'],
                        actual=None,
                        passed=False
                    )
                    self.results.append(result)
                    if fail_fast:
                        logger.info(f"Stopping after exception on expression {idx + 1}")
                        break

        finally:
            self.interactor.close()

        logger.info(f"Test run complete. {sum(1 for r in self.results if r.passed)} passed, "
                   f"{sum(1 for r in self.results if not r.passed)} failed")
        logger.debug(f"Total results: {len(self.results)}, passed: {sum(1 for r in self.results if r.passed)}")

        return self.results

    def get_report(self) -> str:
        """Generate a summary report of the test run."""
        if not self.results:
            return "No tests run yet."

        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)

        report_lines = [
            "=" * 60,
            "Calculator Test Report",
            "=" * 60,
            f"Total: {total} | Passed: {passed} | Failed: {failed}",
            "-" * 60,
            "",
            "Test Results:",
            "-" * 60,
        ]

        for result in self.results:
            status = "PASS" if result.passed else "FAIL"
            report_lines.append(
                f"[{status}] {result.expression.ljust(30)} Expected: {result.expected.ljust(10)} Actual: {result.actual or 'N/A'}"
            )

        report_lines.extend([
            "",
            "=" * 60,
        ])

        return "\n".join(report_lines)

    def save_report(self, output_path: Optional[str] = None) -> None:
        """Save results to a CSV file.

        Args:
            output_path: Optional path to the output CSV file.
                If None, uses current date in filename.
        """
        if not self.results:
            logger.warning("No results to save")
            return

        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"calculator_test_results_{timestamp}.csv"

        results_data = [
            {
                'expression': r.expression,
                'expected': r.expected,
                'actual': r.actual or '',
                'passed': str(r.passed)
            }
            for r in self.results
        ]

        save_results(results_data, output_path)
        logger.info(f"Results saved to {output_path}")


def main():
    """Main entry point for running tests."""
    import argparse

    parser = argparse.ArgumentParser(description="Run Windows Calculator batch expression tests")
    parser.add_argument(
        "csv_file",
        help="Path to CSV file with test expressions"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output CSV file for results (default: auto-generated filename)"
    )
    parser.add_argument(
        "-c", "--calculator",
        help="Path to calculator executable (default: system default)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "-f", "--fail-fast",
        action="store_true",
        help="Stop on first failure"
    )

    args = parser.parse_args()

    # Setup logging
    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)



    # Load expressions
    if not validate_csv_file(args.csv_file):
        sys.exit(1)

    try:
        expressions = load_csv_expressions(args.csv_file)
    except OSError as e:
        logger.error("Failed to load CSV: %s", e)
        sys.exit(1)

    if not expressions:
        logger.error("No valid expressions found in CSV")
        sys.exit(1)

    # Run tests
    runner = CalculatorTestRunner(calculator_path=args.calculator)
    results = runner.run_tests(expressions, fail_fast=args.fail_fast)

    # Generate report
    report = runner.get_report()
    print(report)

    # Save results
    runner.save_report(args.output)

    # Exit with appropriate code
    if any(not r.passed for r in results):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
