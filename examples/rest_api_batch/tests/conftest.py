"""
Pytest fixtures for REST API Batch Processor tests.

This module provides common fixtures for both unit and integration tests.
"""

import sys
from pathlib import Path

# Add parent directory to path for importing steps
sys.path.insert(0, str(Path(__file__).parent.parent))
