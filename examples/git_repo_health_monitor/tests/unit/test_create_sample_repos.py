"""Unit tests for deterministic sample repository setup."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from rpacore import SystemException
from create_sample_repos import _run_git


class TestCreateSampleRepos:
    def test_wraps_missing_git_as_system_exception(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(SystemException, match="git command not found"):
                _run_git(["init"])
