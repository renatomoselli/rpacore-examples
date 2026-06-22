"""Integration test: full RPA Core workflow with mocked Calculator."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock

from rpacore import Engine, ProcessContext, Status, Transaction

from skills.open_calculator import OpenCalculator
from skills.load_expressions import LoadExpressions
from skills.process_expressions import ProcessExpressions
from skills.write_report import WriteReport
from skills.close_calculator import CloseCalculator
from skills.move_file import MoveFile


def _build_transaction():
    return Transaction(
        reference="calc-batch",
        skills=[
            LoadExpressions(name="load_expressions", execution_order=1),
            OpenCalculator(name="open_calculator", execution_order=2),
            ProcessExpressions(name="process_expressions", execution_order=3),
            CloseCalculator(name="close_calculator", execution_order=4),
            WriteReport(name="write_report", execution_order=5),
            MoveFile(name="move_file", execution_order=6),
        ],
    )


def _mock_interactor(results_map: dict[str, str]):
    """Create a CalculatorInteractor mock that returns pre-configured results."""
    mock = MagicMock()
    mock.launch.return_value = True

    last_typed = {"expr": None}

    def _type(expr):
        last_typed["expr"] = expr
        return expr

    def _get_result():
        return results_map.get(last_typed["expr"])

    mock.type_expression.side_effect = _type
    mock.get_result.side_effect = _get_result
    return mock


def test_full_workflow_pass_and_fail(tmp_path):
    """Two expressions: one passes, one fails. Report written, calculator closed."""
    csv_file = tmp_path / "expressions.csv"
    csv_file.write_text(
        "expression,expected_result\n2+2,4\n5*3,99\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    done_dir = tmp_path / "done"
    config = {
        "input_dir": str(tmp_path),
        "output_dir": str(output_dir),
        "done_dir": str(done_dir),
    }

    interactor = _mock_interactor({"2+2": "4", "5*3": "15"})

    tx = Transaction(
        reference="calc-batch",
        skills=[
            LoadExpressions(name="load_expressions", execution_order=1),
            ProcessExpressions(name="process_expressions", execution_order=2),
            CloseCalculator(name="close_calculator", execution_order=3),
            WriteReport(name="write_report", execution_order=4),
            MoveFile(name="move_file", execution_order=5),
        ],
    )
    tx.state["file_path"] = str(csv_file)
    ctx = ProcessContext(transaction=tx, config=config)
    ctx.resources["interactor"] = interactor

    Engine(max_retries=0).run(ctx)

    assert tx.status == Status.FAILED
    assert "results" in tx.state
    assert len(tx.state["results"]) == 2
    assert tx.state["results"][0]["passed"] is True
    assert tx.state["results"][1]["passed"] is False
    json.dumps(tx.state)

    # Report written
    report_path = Path(tx.state["report_path"])
    assert report_path.exists()

    with report_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["passed"] == "True"
    assert rows[1]["passed"] == "False"

    # Calculator closed
    assert csv_file.exists()
    assert not (done_dir / csv_file.name).exists()
    interactor.close.assert_called_once()


def test_validation_failure_skips_downstream(tmp_path):
    """Missing columns triggers BusinessException; downstream skills skip."""
    csv_file = tmp_path / "bad.csv"
    csv_file.write_text("wrong,columns\n1,2\n", encoding="utf-8")

    config = {
        "input_dir": str(tmp_path),
        "output_dir": str(tmp_path / "output"),
    }

    interactor = MagicMock()
    interactor.launch.return_value = True

    tx = Transaction(
        reference="calc-bad",
        skills=[
            LoadExpressions(name="load_expressions", execution_order=1),
            OpenCalculator(name="open_calculator", execution_order=2),
            ProcessExpressions(name="process_expressions", execution_order=3),
            CloseCalculator(name="close_calculator", execution_order=4),
            WriteReport(name="write_report", execution_order=5),
            MoveFile(name="move_file", execution_order=6),
        ],
    )
    tx.state["file_path"] = str(csv_file)
    ctx = ProcessContext(transaction=tx, config=config)
    ctx.resources["interactor"] = interactor

    Engine(max_retries=0).run(ctx)

    assert tx.status == Status.FAILED
    assert tx.state.get("validation_failed") is True
    assert "results" not in tx.state
    assert "report_path" not in tx.state
    # Validation fails before Calculator is opened.
    interactor.launch.assert_not_called()
    interactor.close.assert_not_called()


def test_move_file_moves_to_done(tmp_path):
    """Processed CSV is moved to done/ after successful transaction."""
    csv_file = tmp_path / "expressions.csv"
    csv_file.write_text(
        "expression,expected_result\n2+2,4\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    done_dir = tmp_path / "done"
    config = {
        "input_dir": str(tmp_path),
        "output_dir": str(output_dir),
        "done_dir": str(done_dir),
    }

    interactor = _mock_interactor({"2+2": "4"})

    tx = Transaction(
        reference="calc-move",
        skills=[
            LoadExpressions(name="load_expressions", execution_order=1),
            ProcessExpressions(name="process_expressions", execution_order=2),
            CloseCalculator(name="close_calculator", execution_order=3),
            WriteReport(name="write_report", execution_order=4),
            MoveFile(name="move_file", execution_order=5),
        ],
    )
    tx.state["file_path"] = str(csv_file)
    ctx = ProcessContext(transaction=tx, config=config)
    ctx.resources["interactor"] = interactor

    Engine(max_retries=0).run(ctx)

    assert tx.status == Status.SUCCESSFUL
    assert not csv_file.exists()  # original moved
    done_file = done_dir / csv_file.name
    assert done_file.exists()
    assert tx.state.get("moved_file") == str(done_file)
    interactor.close.assert_called_once()


def test_short_csv_row_is_loaded_without_attribute_error(tmp_path):
    """A missing trailing value is normalized to an empty expected result."""
    csv_file = tmp_path / "short-row.csv"
    csv_file.write_text("expression,expected_result\n2+2\n", encoding="utf-8")
    tx = Transaction(
        reference="short-row",
        skills=[LoadExpressions(name="load_expressions", execution_order=1)],
    )
    tx.state["file_path"] = str(csv_file)

    Engine(max_retries=0).run(
        ProcessContext(transaction=tx, config={"input_dir": str(tmp_path)})
    )

    assert tx.status == Status.SUCCESSFUL
    assert tx.state["expressions"][0]["expected_result"] == ""


def test_load_rejects_source_outside_input_dir(tmp_path):
    """Persisted queue payloads cannot read files outside the configured inbox."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("expression,expected_result\n2+2,4\n", encoding="utf-8")
    tx = Transaction(
        reference="outside",
        skills=[LoadExpressions(name="load_expressions", execution_order=1)],
    )
    tx.state["file_path"] = str(outside)

    Engine(max_retries=0).run(
        ProcessContext(transaction=tx, config={"input_dir": str(input_dir)})
    )

    assert tx.status == Status.FAILED
    assert "expressions" not in tx.state
