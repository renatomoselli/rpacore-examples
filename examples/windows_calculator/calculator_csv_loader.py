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
    """
    if not validate_csv_file(csv_path):
        raise ValueError(f"Invalid CSV file: {csv_path}")

    expressions = []
    
    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            try:
                expression = row.get('expression', '').strip()
                expected_result = row.get('expected_result', '').strip()
                
                if not expression:
                    logger.warning(f"Row {row_num}: Empty expression, skipping")
                    continue
                
                expressions.append({
                    'expression': expression,
                    'expected_result': expected_result,
                    'row': row_num
                })
                
            except Exception as e:
                logger.error(f"Row {row_num}: Failed to parse: {e}")
                continue
    
    logger.info(f"Loaded {len(expressions)} expressions from {csv_path}")
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
                logger.error(f"Missing required columns: {missing}")
                return False
            
            return True
            
    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_path}")
        return False
    except Exception as e:
        logger.error(f"Failed to validate CSV: {e}")
        return False


def save_results(results: List[Dict[str, Any]], output_path: str) -> None:
    """Save test results to a CSV file.
    
    Args:
        results: List of result dictionaries with 'expression', 'actual', 'expected', 'passed' keys.
        output_path: Path to the output CSV file.
    """
    fieldnames = ['expression', 'expected', 'actual', 'passed']
    
    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
    except OSError as e:
        logger.error(f"Failed to save results to {output_path}: {e}")
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
