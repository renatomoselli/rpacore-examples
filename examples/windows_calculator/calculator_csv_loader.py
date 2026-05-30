"""CSV loader for calculator test expressions.

This module provides CSV parsing and test data loading utilities.
"""
from typing import List, Dict, Any
from pathlib import Path
import csv
import logging

logger = logging.getLogger(__name__)


def load_csv_expressions(csv_path: str) -> List[Dict[str, Any]]:
    """Load test expressions from a CSV file.
    
    Args:
        csv_path: Path to the CSV file.
            Expected columns: expression, expected_result
    
    Returns:
        List of dictionaries with 'expression' and 'expected_result' keys.
    
    Raises:
        ValueError: If the file is missing or lacks required columns.
    """
    try:
        f = open(csv_path, 'r', newline='', encoding='utf-8')
    except OSError as exc:
        raise ValueError(f"Unable to open CSV file {csv_path}: {exc}") from exc
    
    expressions = []
    
    with f:
        reader = csv.DictReader(f)
        
        required_columns = {'expression', 'expected_result'}
        actual_columns = set(reader.fieldnames) if reader.fieldnames else set()
        if not required_columns.issubset(actual_columns):
            missing = required_columns - actual_columns
            raise ValueError(f"Missing required columns: {missing}")
        
        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            expression = row.get('expression', '').strip()
            expected_result = row.get('expected_result', '').strip()
            
            if not expression:
                logger.warning("Row %d: Empty expression, skipping", row_num)
                continue
            
            expressions.append({
                'expression': expression,
                'expected_result': expected_result,
                'row': row_num
            })
    
    logger.info("Loaded %d expressions from %s", len(expressions), csv_path)
    return expressions


def validate_csv_file(csv_path: str) -> bool:
    """Validate a CSV file has the required columns.
    
    Args:
        csv_path: Path to the CSV file.
    
    Returns:
        True if file is valid, False otherwise.
    """
    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            required_columns = {'expression', 'expected_result'}
            actual_columns = set(reader.fieldnames) if reader.fieldnames else set()
            
            if not required_columns.issubset(actual_columns):
                missing = required_columns - actual_columns
                logger.error("Missing required columns: %s", missing)
                return False
            
            return True
            
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        logger.error("Failed to validate CSV: %s", e)
        return False


def save_results(results: List[Dict[str, Any]], output_path: str) -> None:
    """Save test results to a CSV file.
    
    Args:
        results: List of result dictionaries with 'expression', 'actual', 'expected', 'passed' keys.
        output_path: Path to the output CSV file.
    """
    fieldnames = ['expression', 'expected_result', 'actual', 'passed']
    
    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
    except OSError as e:
        logger.error("Failed to save results to %s: %s", output_path, e)
        raise


if __name__ == "__main__":
    # Test with a sample CSV file
    import sys
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
        if validate_csv_file(csv_path):
            expressions = load_csv_expressions(csv_path)
            print(f"Loaded {len(expressions)} expressions")
        else:
            print("Invalid CSV file")
