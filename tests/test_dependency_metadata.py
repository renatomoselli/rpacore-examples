from __future__ import annotations

from pathlib import Path
import tomllib


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_ROOT = REPOSITORY_ROOT / "examples"
RPACORE_REQUIREMENT = "rpacore>=0.2.0,<0.3.0"
REQUIREMENTS_FILES = (
    "acme_work_items/requirements.txt",
    "checkpoint_resume/requirements.txt",
    "database_reconciliation/requirements.txt",
    "excel_reorganization/requirements.txt",
    "file_inbox_processor/requirements.txt",
    "git_repo_health_monitor/requirements.txt",
    "json_event_log_processor/requirements.txt",
    "pdf_invoice_extraction/requirements.txt",
    "rest_api_batch/requirements.txt",
    "rpa_challenge/requirements.txt",
)


def _requirement_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_all_examples_require_rpacore_v02() -> None:
    for relative_path in REQUIREMENTS_FILES:
        assert RPACORE_REQUIREMENT in _requirement_lines(
            EXAMPLES_ROOT / relative_path
        )


def test_package_metadata_matches_example_requirements() -> None:
    for relative_path in (
        "checkpoint_resume/pyproject.toml",
        "json_event_log_processor/pyproject.toml",
    ):
        metadata = tomllib.loads(
            (EXAMPLES_ROOT / relative_path).read_text(encoding="utf-8")
        )
        assert RPACORE_REQUIREMENT in metadata["project"]["dependencies"]

    setup_py = (EXAMPLES_ROOT / "windows_calculator/setup.py").read_text(
        encoding="utf-8"
    )
    assert f'"{RPACORE_REQUIREMENT}"' in setup_py
