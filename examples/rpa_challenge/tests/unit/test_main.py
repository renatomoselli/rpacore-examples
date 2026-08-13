from __future__ import annotations

"""Unit tests for main.py helpers."""

from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

import main as rpa_main
from rpacore import Status, SystemException
from main import _browser_page_available, _display_path, _format_failed_steps, _stop_playwright
from steps.row import FillRow, SubmitRow

pytestmark = pytest.mark.unit

VALID_CONFIG = {
    "max_retries": 2,
    "log_level": "INFO",
    "transaction_db_path": "rpacore.db",
}


def test_stop_playwright_stops_and_removes_runtime_handle():
    pw = Mock()
    shared_resources = {"_pw": pw}

    _stop_playwright(shared_resources)

    pw.stop.assert_called_once()
    assert "_pw" not in shared_resources


def test_stop_playwright_is_idempotent():
    shared_resources = {}

    _stop_playwright(shared_resources)

    assert shared_resources == {}


def test_browser_page_available_rejects_missing_or_closed_page():
    open_page = Mock()
    open_page.is_closed.return_value = False
    closed_page = Mock()
    closed_page.is_closed.return_value = True
    invalid_page = object()

    assert _browser_page_available({"page": open_page}) is True
    assert _browser_page_available({"page": closed_page}) is False
    assert _browser_page_available({"page": invalid_page}) is False
    assert _browser_page_available({}) is False


def test_display_path_prefers_project_relative_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(rpa_main, "PROJECT_ROOT", tmp_path)
    db_path = tmp_path / "rpacore.db"

    assert _display_path(str(db_path)) == "rpacore.db"


def test_format_failed_steps_returns_none_when_no_failures():
    tx = Mock()
    tx.failed_steps.return_value = []

    assert _format_failed_steps(tx) == "none"


def test_format_failed_steps_includes_step_names_and_classes():
    fill = FillRow("fill_row", 1, arguments={"row": {}})
    submit = SubmitRow("submit_row", 2)
    fill.status = Status.FAILED
    submit.status = Status.FAILED

    assert _format_failed_steps(Mock(failed_steps=lambda: [fill, submit])) == (
        "fill_row(FillRow); submit_row(SubmitRow)"
    )


def test_format_failed_steps_keeps_registered_name_when_class_differs():
    step = Mock(name="custom_registered_step")
    step.name = "custom_registered_step"

    assert _format_failed_steps(Mock(failed_steps=lambda: [step])) == (
        "custom_registered_step(Mock)"
    )


def test_validate_config_accepts_required_keys():
    assert rpa_main._validate_config(dict(VALID_CONFIG)) == VALID_CONFIG


@pytest.mark.parametrize(
    ("config", "key"),
    [
        ({k: v for k, v in VALID_CONFIG.items() if k != "transaction_db_path"}, "transaction_db_path"),
        ({**VALID_CONFIG, "max_retries": "2"}, "max_retries"),
        ({**VALID_CONFIG, "max_retries": True}, "max_retries"),
        ({**VALID_CONFIG, "max_retries": -1}, "max_retries"),
        ({**VALID_CONFIG, "max_page_load_retries": 0}, "max_page_load_retries"),
        ({**VALID_CONFIG, "timeout_click": 0}, "timeout_click"),
        ({**VALID_CONFIG, "headless": "true"}, "headless"),
        ({**VALID_CONFIG, "log_level": ""}, "log_level"),
        ({**VALID_CONFIG, "transaction_db_path": ""}, "transaction_db_path"),
        ({**VALID_CONFIG, "xlsx_url": ""}, "xlsx_url"),
        ({**VALID_CONFIG, "log_level": "   "}, "log_level"),
        ({**VALID_CONFIG, "screenshot_dir": 42}, "screenshot_dir"),
        ({**VALID_CONFIG, "xlsx_allowed_hosts": 123}, "xlsx_allowed_hosts"),
        ({**VALID_CONFIG, "xlsx_allowed_hosts": ["www.rpachallenge.com", 123]}, "xlsx_allowed_hosts"),
    ],
)
def test_validate_config_rejects_invalid_values(config, key):
    with pytest.raises(SystemException) as exc_info:
        rpa_main._validate_config(config)

    assert key in str(exc_info.value)


def test_validate_config_projects_all_consumed_options_without_mutating_input():
    config = {
        **VALID_CONFIG,
        "screenshot_dir": "screenshots",
        "xlsx_url": "https://www.rpachallenge.com/assets/downloadFiles/challenge.xlsx",
        "xlsx_allowed_hosts": ["www.rpachallenge.com"],
        "max_page_load_retries": 1,
        "headless": True,
        "timeout_page_load": 1,
        "timeout_click": 1,
        "timeout_form_transition": 1,
        "timeout_congratulations_check": 1,
        "timeout_score_extraction": 1,
        "unsupported_option": "ignored",
    }
    original = deepcopy(config)

    validated = rpa_main._validate_config(config)

    assert config == original
    assert "unsupported_option" not in validated
    assert validated["timeout_score_extraction"] == 1


def test_load_example_config_requires_project_root_file_and_contained_paths(
    tmp_path, monkeypatch
):
    project_root = tmp_path / "example"
    project_root.mkdir()
    config = {**VALID_CONFIG, "screenshot_dir": "screenshots"}
    loaded_paths = []
    monkeypatch.setattr(rpa_main, "PROJECT_ROOT", project_root)
    monkeypatch.chdir(tmp_path)

    def fake_load_config(path, *, require_file):
        loaded_paths.append(path)
        assert require_file is True
        return config

    monkeypatch.setattr(rpa_main, "load_config", fake_load_config)

    validated = rpa_main._load_example_config()

    assert loaded_paths == [project_root / "config.toml"]
    assert validated["transaction_db_path"] == str(project_root / "rpacore.db")
    assert validated["screenshot_dir"] == str(project_root / "screenshots")


@pytest.mark.parametrize("key", ("transaction_db_path", "screenshot_dir"))
def test_load_example_config_rejects_owned_paths_outside_project_root(
    tmp_path, monkeypatch, key
):
    config = {**VALID_CONFIG, key: "../outside"}
    monkeypatch.setattr(rpa_main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        rpa_main, "load_config", lambda _path, *, require_file: config
    )

    with pytest.raises(SystemException, match=f"{key} resolves outside root"):
        rpa_main._load_example_config()


def test_load_example_config_propagates_missing_required_file(tmp_path, monkeypatch):
    monkeypatch.setattr(rpa_main, "PROJECT_ROOT", tmp_path)

    with pytest.raises(FileNotFoundError, match="config.toml"):
        rpa_main._load_example_config()


def test_main_aborts_when_row_transaction_fails(monkeypatch, tmp_path, capsys):
    config = {
        "max_retries": 2,
        "log_level": "INFO",
        "transaction_db_path": "transactions.db",
        "screenshot_dir": "",
        "headless": True,
    }
    engine_runs: list[str] = []
    engine_max_retries: list[int] = []

    class FakeEngine:
        def __init__(self, max_retries=0, **_kwargs):
            engine_max_retries.append(max_retries)

        def run(self, ctx):
            tx = ctx.transaction
            engine_runs.append(tx.reference)
            if tx.reference == "rpa-challenge-setup":
                page = Mock()
                page.is_closed.return_value = False
                ctx.resources["page"] = page
                tx.state["rows"] = [
                    {
                        "First Name": "Jane",
                        "Last Name": "Doe",
                        "Company Name": "ACME",
                        "Role in Company": "Engineer",
                        "Address": "1 Test St",
                        "Email": "jane@example.com",
                        "Phone Number": "555-0100",
                    }
                ]
                tx.status = Status.SUCCESSFUL
                return
            if tx.reference.startswith("rpa-row-"):
                tx.status = Status.FAILED
                tx.steps[0].status = Status.FAILED
                return
            tx.status = Status.SUCCESSFUL

    monkeypatch.setattr(
        rpa_main, "load_config", lambda _path, *, require_file: config
    )
    monkeypatch.setattr(rpa_main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(rpa_main, "configure_logger", lambda **_kwargs: None)
    monkeypatch.setattr(rpa_main, "Engine", FakeEngine)
    monkeypatch.setattr(rpa_main, "save_transaction", lambda *_args, **_kwargs: None)

    with pytest.raises(SystemExit) as exc_info:
        rpa_main.main()

    assert exc_info.value.code == 1
    assert engine_max_retries == [2, 0]
    assert engine_runs == ["rpa-challenge-setup", "rpa-row-1-jane@example.com"]
    assert "Row 1 failed" in capsys.readouterr().out


def test_main_shares_browser_resources_across_transactions(monkeypatch, tmp_path, capsys):
    config = {
        "max_retries": 2,
        "log_level": "INFO",
        "transaction_db_path": "transactions.db",
        "screenshot_dir": "",
        "headless": True,
    }
    observed_pages: list[object] = []
    run_order: list[str] = []
    page = Mock()
    page.is_closed.return_value = False

    class FakeEngine:
        def __init__(self, max_retries=0, **_kwargs):
            self.max_retries = max_retries

        def run(self, ctx):
            run_order.append(ctx.transaction.reference)
            if ctx.transaction.reference == "rpa-challenge-setup":
                ctx.resources["page"] = page
                ctx.transaction.state["rows"] = [
                    {
                        "First Name": "Jane",
                        "Last Name": "Doe",
                        "Company Name": "ACME",
                        "Role in Company": "Engineer",
                        "Address": "1 Test St",
                        "Email": "jane@example.com",
                        "Phone Number": "555-0100",
                    }
                ]
            elif ctx.transaction.reference.startswith("rpa-row-"):
                observed_pages.append(ctx.resources.get("page"))
            elif ctx.transaction.reference == "rpa-challenge-score":
                observed_pages.append(ctx.resources.get("page"))
                ctx.transaction.state["score"] = "100%"
            ctx.transaction.status = Status.SUCCESSFUL

    monkeypatch.setattr(
        rpa_main, "load_config", lambda _path, *, require_file: config
    )
    monkeypatch.setattr(rpa_main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(rpa_main, "configure_logger", lambda **_kwargs: None)
    monkeypatch.setattr(rpa_main, "Engine", FakeEngine)
    monkeypatch.setattr(rpa_main, "save_transaction", lambda *_args, **_kwargs: None)

    rpa_main.main()

    assert run_order == [
        "rpa-challenge-setup",
        "rpa-row-1-jane@example.com",
        "rpa-challenge-score",
    ]
    assert observed_pages == [page, page]
    assert "Final score: 100%" in capsys.readouterr().out


def test_main_continues_when_transaction_persistence_warns(monkeypatch, tmp_path, capsys):
    config = {
        "max_retries": 2,
        "log_level": "INFO",
        "transaction_db_path": "transactions.db",
        "screenshot_dir": "",
        "headless": True,
    }
    page = Mock()
    page.is_closed.return_value = False

    class FakeEngine:
        def __init__(self, max_retries=0, **_kwargs):
            self.max_retries = max_retries

        def run(self, ctx):
            if ctx.transaction.reference == "rpa-challenge-setup":
                ctx.resources["page"] = page
                ctx.transaction.state["rows"] = [
                    {
                        "First Name": "Jane",
                        "Last Name": "Doe",
                        "Company Name": "ACME",
                        "Role in Company": "Engineer",
                        "Address": "1 Test St",
                        "Email": "jane@example.com",
                        "Phone Number": "555-0100",
                    }
                ]
            elif ctx.transaction.reference == "rpa-challenge-score":
                ctx.transaction.state["score"] = "100%"
            ctx.transaction.status = Status.SUCCESSFUL

    monkeypatch.setattr(
        rpa_main, "load_config", lambda _path, *, require_file: config
    )
    monkeypatch.setattr(rpa_main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(rpa_main, "configure_logger", lambda **_kwargs: None)
    monkeypatch.setattr(rpa_main, "Engine", FakeEngine)
    monkeypatch.setattr(rpa_main, "save_transaction", Mock(side_effect=OSError("locked")))

    rpa_main.main()

    assert rpa_main.save_transaction.call_count == 3
    assert "Final score: 100%" in capsys.readouterr().out


def test_main_aborts_when_score_transaction_records_no_score(monkeypatch, tmp_path, capsys):
    config = {
        "max_retries": 2,
        "log_level": "INFO",
        "transaction_db_path": "transactions.db",
        "screenshot_dir": "",
        "headless": True,
    }
    page = Mock()
    page.is_closed.return_value = False

    class FakeEngine:
        def __init__(self, max_retries=0, **_kwargs):
            self.max_retries = max_retries

        def run(self, ctx):
            if ctx.transaction.reference == "rpa-challenge-setup":
                ctx.resources["page"] = page
                ctx.transaction.state["rows"] = [
                    {
                        "First Name": "Jane",
                        "Last Name": "Doe",
                        "Company Name": "ACME",
                        "Role in Company": "Engineer",
                        "Address": "1 Test St",
                        "Email": "jane@example.com",
                        "Phone Number": "555-0100",
                    }
                ]
            ctx.transaction.status = Status.SUCCESSFUL

    monkeypatch.setattr(
        rpa_main, "load_config", lambda _path, *, require_file: config
    )
    monkeypatch.setattr(rpa_main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(rpa_main, "configure_logger", lambda **_kwargs: None)
    monkeypatch.setattr(rpa_main, "Engine", FakeEngine)
    monkeypatch.setattr(rpa_main, "save_transaction", lambda *_args, **_kwargs: None)

    with pytest.raises(SystemExit) as exc_info:
        rpa_main.main()

    assert exc_info.value.code == 1
    assert "Score capture completed but no score was recorded." in capsys.readouterr().out


def test_main_aborts_when_browser_page_is_closed_before_row(monkeypatch, tmp_path, capsys):
    config = {
        "max_retries": 2,
        "log_level": "INFO",
        "transaction_db_path": "transactions.db",
        "screenshot_dir": "",
        "headless": True,
    }
    closed_page = Mock()
    closed_page.is_closed.return_value = True

    class FakeEngine:
        def __init__(self, max_retries=0, **_kwargs):
            self.max_retries = max_retries

        def run(self, ctx):
            if ctx.transaction.reference == "rpa-challenge-setup":
                ctx.resources["page"] = closed_page
                ctx.transaction.state["rows"] = [
                    {
                        "First Name": "Jane",
                        "Last Name": "Doe",
                        "Company Name": "ACME",
                        "Role in Company": "Engineer",
                        "Address": "1 Test St",
                        "Email": "jane@example.com",
                        "Phone Number": "555-0100",
                    }
                ]
            ctx.transaction.status = Status.SUCCESSFUL

    monkeypatch.setattr(
        rpa_main, "load_config", lambda _path, *, require_file: config
    )
    monkeypatch.setattr(rpa_main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(rpa_main, "configure_logger", lambda **_kwargs: None)
    monkeypatch.setattr(rpa_main, "Engine", FakeEngine)
    monkeypatch.setattr(rpa_main, "save_transaction", lambda *_args, **_kwargs: None)

    with pytest.raises(SystemExit) as exc_info:
        rpa_main.main()

    assert exc_info.value.code == 1
    assert "Browser session is not available before row 1" in capsys.readouterr().out
