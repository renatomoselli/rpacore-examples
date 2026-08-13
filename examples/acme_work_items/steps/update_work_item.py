from __future__ import annotations

from rpacore import BusinessException, ProcessContext, Step, SystemException

from steps._session import RemoteConflictError, require_authenticated_session


class UpdateWorkItem(Step):
    """Apply and post-verify the intended security hash replay-safely."""

    def execute(self, ctx: ProcessContext) -> None:
        work_item_id = ctx.require_state("work_item_id", str, action=self.name)
        expected_hash = ctx.require_state("fetched_hash", str, action=self.name)
        security_hash = ctx.require_state("security_hash", str, action=self.name)
        ctx.require_state("update_intent_id", str, action=self.name)

        try:
            item = require_authenticated_session(ctx).apply_security_hash(
                work_item_id,
                expected_hash=expected_hash,
                security_hash=security_hash,
            )
        except RemoteConflictError as exc:
            raise BusinessException(
                "Work item changed before the security-hash update",
                action=self.name,
                halts_remaining_steps=True,
            ) from exc
        except SystemException:
            raise
        except Exception as exc:
            raise SystemException("Unable to update ACME work item", action=self.name) from exc

        if item.status == "closed":
            raise BusinessException(
                "Work item is already closed without durable close intent",
                action=self.name,
                halts_remaining_steps=True,
            )
        if (
            item.identity_hash != security_hash
            or item.stored_comment != security_hash
            or item.status != "open"
        ):
            raise SystemException("Updated work item could not be verified", action=self.name)
        # Persist audit evidence and the exact close precondition for resume.
        ctx.state["update_applied"] = True
        ctx.state["updated_hash"] = item.fingerprint
        ctx.state["close_intent"] = {
            "work_item_id": work_item_id,
            "expected_hash": item.fingerprint,
            "security_hash": security_hash,
        }
