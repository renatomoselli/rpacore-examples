"""Load and validate sales data from CSV file.

This skill reads a flat CSV file with columns (Employee Name, Date, Amount, Country),
validates the schema, and stores the data in ctx.state["sales_data"] as a list of dicts.

Pattern: Follows examples/json_event_log_processor/skills/load_json_file.py:16-52
"""

from __future__ import annotations
import csv
import datetime
from pathlib import Path
from rpacore import BusinessException, ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)


class LoadSalesData(Skill):
    """Load and validate sales data from CSV file."""

    def execute(self, ctx: ProcessContext) -> None:
        """Load CSV file, validate schema, and store data in context."""
        csv_path = ctx.require_config("csv_path", str, action=self.name)

        csv_path = str(Path(csv_path).resolve())

        try:
            with open(csv_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                # Filter empty rows and strip whitespace
                rows = []
                for row in reader:
                    normalized_row = {
                        key: value.strip() if isinstance(value, str) else ""
                        for key, value in row.items()
                    }
                    if any(value for value in normalized_row.values()):
                        rows.append(normalized_row)
        except FileNotFoundError as exc:
            raise SystemException(f"CSV file not found: {csv_path}", action=self.name) from exc
        except csv.Error as exc:
            raise SystemException(f"Invalid CSV format in {csv_path}: {exc}", action=self.name) from exc
        except OSError as exc:
            raise SystemException(f"Failed to read CSV file {csv_path}: {exc}", action=self.name) from exc
        except Exception as exc:
            raise SystemException(f"Unexpected error reading {csv_path}: {exc}", action=self.name) from exc

        if not rows:
            raise BusinessException("CSV file contains no data rows.", action=self.name)

        # Validate schema
        self._validate_schema(rows, csv_path)

        # Store data in context
        ctx.state["sales_data"] = rows
        logger.info("Loaded %d rows from %s", len(rows), csv_path)

    def _validate_schema(self, rows: list[dict], csv_path: str) -> None:
        """Validate that CSV has expected columns with correct data types."""
        REQUIRED_COLUMNS = {
            "employee_name": str,
            "date": str,  # YYYY-MM-DD format, validated in _parse_date
            "amount": (int, float),
            "country": str,
        }

        # Check all required columns exist in first row
        first_row = rows[0]
        missing_columns = set(REQUIRED_COLUMNS.keys()) - set(first_row.keys())
        if missing_columns:
            raise SystemException(
                f"CSV missing required columns: {missing_columns}",
                action=self.name,
            )

        # Validate data types and check all rows have required columns
        for i, row in enumerate(rows):
            # Check all required columns exist in this row
            missing_cols = set(REQUIRED_COLUMNS.keys()) - set(row.keys())
            if missing_cols:
                raise SystemException(
                    f"Row {i + 1} missing required columns: {missing_cols}",
                    action=self.name,
                )

            # Validate data types and convert to correct types
            for column, expected_type in REQUIRED_COLUMNS.items():
                value = row.get(column)
                if value is None:
                    continue
                if expected_type is str and value == "":
                    raise BusinessException(
                        f"Row {i + 1} missing required value for column '{column}'",
                        action=self.name,
                    )

                try:
                    if isinstance(expected_type, tuple):
                        # Convert to first matching type
                        converted = None
                        for t in expected_type:
                            try:
                                if isinstance(value, str):
                                    converted = t(value)
                                elif isinstance(value, t):
                                    converted = value
                                else:
                                    raise ValueError(f"Cannot convert {value!r} to {t}")
                                break
                            except (ValueError, TypeError):
                                continue
                        if converted is None:
                            raise ValueError(f"Cannot convert {value!r} to any of {expected_type}")
                        row[column] = converted
                    elif isinstance(value, str):
                        # Convert string to expected type
                        row[column] = expected_type(value)
                    elif not isinstance(value, expected_type):
                        raise ValueError(f"Expected {expected_type}, got {type(value)}")
                except (ValueError, TypeError) as exc:
                    raise BusinessException(
                        f"Row {i + 1} has invalid value for column '{column}': {value!r}",
                        action=self.name,
                    ) from exc

            # Normalize amount to float for consistent arithmetic
            if "amount" in row and row["amount"] is not None:
                row["amount"] = float(row["amount"])

        # Validate date format and semantic correctness (YYYY-MM-DD)
        for i, row in enumerate(rows):
            date_str = row.get("date")
            if not date_str:
                raise BusinessException(
                    f"Row {i + 1} missing date field",
                    action=self.name,
                    stop=True,
                )
            try:
                datetime.datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError as exc:
                raise BusinessException(
                    f"Row {i + 1} has invalid date format: {date_str!r} (expected YYYY-MM-DD)",
                    action=self.name,
                    stop=True,
                ) from exc
