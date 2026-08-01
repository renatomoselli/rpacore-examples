from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path


EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"
EXPECTED_IDENTITIES = {
    "acme_work_items": [
        ("ITEM_DEFINITION_IDENTITY", "acme-work-items/item/v1"),
        ("SUMMARY_DEFINITION_IDENTITY", "acme-work-items/summary/v1"),
    ],
    "checkpoint_resume": [("DEFINITION_IDENTITY", "checkpoint-resume/v1")],
    "database_reconciliation": [
        ("SETUP_DEFINITION_IDENTITY", "database-reconciliation/setup/v1"),
        ("PAYMENT_DEFINITION_IDENTITY", "database-reconciliation/payment/v1"),
        ("REPORT_DEFINITION_IDENTITY", "database-reconciliation/report/v1"),
    ],
    "excel_reorganization": [("DEFINITION_IDENTITY", "excel-reorganization/v1")],
    "file_inbox_processor": [
        ("DEFINITION_IDENTITY", "file-inbox-processor/report/v1")
    ],
    "git_repo_health_monitor": [
        ("REPOSITORY_DEFINITION_IDENTITY", "git-repo-health-monitor/repository/v1"),
        ("SUMMARY_DEFINITION_IDENTITY", "git-repo-health-monitor/summary/v1"),
    ],
    "json_event_log_processor": [
        ("ERROR_REPORT_DEFINITION_IDENTITY", "json-event-log-processor/error-report/v1"),
        ("FILE_DEFINITION_IDENTITY", "json-event-log-processor/file/v1"),
    ],
    "pdf_invoice_extraction": [
        ("DEFINITION_IDENTITY", "pdf-invoice-extraction/invoice/v1")
    ],
    "rest_api_batch": [
        ("FETCH_DEFINITION_IDENTITY", "rest-api-batch/fetch/v1"),
        ("POST_DEFINITION_IDENTITY", "rest-api-batch/post/v1"),
    ],
    "rpa_challenge": [
        ("SETUP_DEFINITION_IDENTITY", "rpa-challenge/setup/v1"),
        ("ROW_DEFINITION_IDENTITY", "rpa-challenge/row/v1"),
        ("SCORE_DEFINITION_IDENTITY", "rpa-challenge/score/v1"),
    ],
    "windows_calculator": [("DEFINITION_IDENTITY", "windows-calculator/batch/v1")],
}


def _module(example: str) -> ast.Module:
    return ast.parse((EXAMPLES_ROOT / example / "main.py").read_text(encoding="utf-8"))


def _keyword_name(call: ast.Call, keyword_name: str) -> str | None:
    keyword = next((item for item in call.keywords if item.arg == keyword_name), None)
    return keyword.value.id if keyword is not None and isinstance(keyword.value, ast.Name) else None


def test_all_production_transactions_use_declared_stable_identities() -> None:
    observed_tokens: set[str] = set()

    for example, expected in EXPECTED_IDENTITIES.items():
        module = _module(example)
        constants = {
            target.id: node.value.value
            for node in module.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance((target := node.targets[0]), ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        }
        assert [(name, constants.get(name)) for name, _ in expected] == expected

        calls = [
            node
            for node in ast.walk(module)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Transaction"
        ]
        assert Counter(
            _keyword_name(call, "definition_identity") for call in calls
        ) == Counter(name for name, _ in expected)
        observed_tokens.update(value for _, value in expected)

    assert len(observed_tokens) == sum(len(values) for values in EXPECTED_IDENTITIES.values())


def test_checkpoint_resume_reuses_creation_identity() -> None:
    module = _module("checkpoint_resume")
    resume_calls = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resume_transaction"
    ]

    assert len(resume_calls) == 1
    assert _keyword_name(resume_calls[0], "definition_identity") == "DEFINITION_IDENTITY"


def test_persisted_integration_transactions_use_example_identities() -> None:
    persisted_call_count = 0

    for integration_test in EXAMPLES_ROOT.glob("*/tests/integration/*.py"):
        module = ast.parse(integration_test.read_text(encoding="utf-8"))
        example = integration_test.parents[2].name
        expected_names = {name for name, _ in EXPECTED_IDENTITIES[example]}

        for function in (
            node
            for node in ast.walk(module)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            saved_names = {
                call.args[0].id
                for call in ast.walk(function)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "save_transaction"
                and call.args
                and isinstance(call.args[0], ast.Name)
            }
            persisted_calls = [
                assignment.value
                for assignment in ast.walk(function)
                if isinstance(assignment, ast.Assign)
                and len(assignment.targets) == 1
                and isinstance(assignment.targets[0], ast.Name)
                and assignment.targets[0].id in saved_names
                and isinstance(assignment.value, ast.Call)
                and isinstance(assignment.value.func, ast.Name)
                and assignment.value.func.id == "Transaction"
            ]
            persisted_call_count += len(persisted_calls)

            for call in persisted_calls:
                identity_name = _keyword_name(call, "definition_identity")
                assert identity_name in expected_names, (
                    f"{integration_test}: persisted Transaction must use one of "
                    f"{sorted(expected_names)}, got {identity_name!r}"
                )

    assert persisted_call_count == 11
