from __future__ import annotations

from pathlib import Path

from rpacore import BusinessException, ProcessContext, Skill, SystemException

from skills._session import RemoteConflictError, require_authenticated_session


class CloseWorkItem(Skill):
    """Close the intended item and recognize a verified replay as success."""

    def execute(self, ctx: ProcessContext) -> None:
        work_item_id = ctx.require_state("work_item_id", str, action=self.name)
        security_hash = ctx.require_state("security_hash", str, action=self.name)
        close_intent = ctx.require_state("close_intent", dict, action=self.name)
        if (
            close_intent.get("work_item_id") != work_item_id
            or close_intent.get("security_hash") != security_hash
            or not isinstance(close_intent.get("expected_hash"), str)
        ):
            raise BusinessException(
                "Close intent does not authorize this remote item",
                action=self.name,
                stop=True,
            )

        session = require_authenticated_session(ctx)
        try:
            item = session.close_item(
                work_item_id,
                expected_hash=str(close_intent["expected_hash"]),
                security_hash=security_hash,
            )
        except RemoteConflictError as exc:
            raise BusinessException(
                "Work item changed before close",
                action=self.name,
                stop=True,
            ) from exc
        except SystemException:
            raise
        except Exception as exc:
            raise SystemException("Unable to close ACME work item", action=self.name) from exc

        if (
            item.status != "closed"
            or item.identity_hash != security_hash
            or item.stored_comment != security_hash
        ):
            raise BusinessException(
                "Closed work item does not match the persisted close intent",
                action=self.name,
                stop=True,
            )
        ctx.state["closed"] = True
        ctx.state["closed_hash"] = item.fingerprint
        ctx.state["idempotency_outcome"] = "already_closed" if item.was_already_closed else "closed"

        screenshot_dir = Path(
            ctx.require_config("screenshot_dir", str, action=self.name)
        )
        path = session.capture_screenshot(
            work_item_id,
            screenshot_dir / f"closed-{work_item_id}.png",
        )
        ctx.add_artifact(
            "closed-work-item",
            str(path),
            kind="screenshot",
            metadata={"work_item_id": work_item_id, "status": "closed"},
        )
