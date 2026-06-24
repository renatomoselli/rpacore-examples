from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from rpacore import CredentialNotFoundError, CredentialProvider, Engine, ProcessContext, Skill, Transaction

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skills._session import BrowserSession
from tests.fake_acme import FakeAcmeServer


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Keep wheel-only validation useful when optional browser deps are absent."""
    if importlib.util.find_spec("playwright") is not None:
        return
    missing = pytest.mark.skip(reason="Playwright is not installed; install requirements-test.txt")
    for item in items:
        if "integration" in item.keywords or "live" in item.keywords:
            item.add_marker(missing)


class FakeCredentials(CredentialProvider):
    def __init__(self, username: str = "robot@example.test", password: str = "correct-horse") -> None:
        self.values = {"acme_username": username, "acme_password": password}

    def get(self, name: str) -> str:
        try:
            return self.values[name]
        except KeyError:
            raise CredentialNotFoundError(f"Missing {name}") from None


@pytest.fixture
def credentials() -> FakeCredentials:
    return FakeCredentials()


@pytest.fixture
def acme_server() -> FakeAcmeServer:
    with FakeAcmeServer() as server:
        yield server


@pytest.fixture
def example_config(tmp_path: Path, acme_server: FakeAcmeServer) -> dict[str, object]:
    return {
        "max_retries": 0,
        "retry_delay": 0.0,
        "retry_backoff": 1.0,
        "log_level": "WARNING",
        "log_format": "text",
        "transaction_db_path": str(tmp_path / "transactions.db"),
        "screenshot_dir": str(tmp_path / "screenshots"),
        "report_dir": str(tmp_path / "reports"),
        "report_max_records": 1000,
        "base_url": acme_server.base_url,
        "credential_provider": "env",
        "headless": True,
        "page_load_timeout_ms": 10000,
        "action_timeout_ms": 5000,
        "queue": {
            "db_path": str(tmp_path / "queue.db"),
            "lease_timeout": 30,
            "max_retries": 0,
        },
    }


def browser_session(config: dict[str, object]) -> BrowserSession:
    return BrowserSession(
        str(config["base_url"]),
        headless=bool(config["headless"]),
        page_load_timeout_ms=int(config["page_load_timeout_ms"]),
        action_timeout_ms=int(config["action_timeout_ms"]),
    )


def run_skill(
    skill: Skill,
    *,
    state: dict[str, object],
    config: dict[str, object],
    resources: dict[str, object] | None = None,
    credentials: CredentialProvider | None = None,
) -> Transaction:
    transaction = Transaction(reference="unit", state=state, skills=[skill])
    Engine(max_retries=0).run(
        ProcessContext(
            transaction=transaction,
            config=config,
            resources=resources or {},
            credentials=credentials or FakeCredentials(),
        )
    )
    return transaction
