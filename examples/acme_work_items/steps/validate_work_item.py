from __future__ import annotations

from rpacore import BusinessException, ProcessContext, Step


class ValidateWorkItem(Step):
    """Reject stale, malformed, closed, or unsupported work items."""

    def execute(self, ctx: ProcessContext) -> None:
        client_id = ctx.require_state("client_id", str, action=self.name).strip()
        wiid = ctx.require_state("wiid", str, action=self.name).strip()
        item_type = ctx.require_state("fetched_type", str, action=self.name)
        status = ctx.require_state("fetched_status", str, action=self.name)
        fetched_hash = ctx.require_state("fetched_hash", str, action=self.name)
        discovered_hash = ctx.require_state("discovered_hash", str, action=self.name)

        if not client_id or not wiid:
            raise BusinessException(
                "Work item is missing client_id or WIID",
                action=self.name,
                halts_remaining_steps=True,
            )
        if item_type != "WI5":
            raise BusinessException(
                f"Unsupported work-item type: {item_type!r}",
                action=self.name,
                halts_remaining_steps=True,
            )
        if status != "open":
            raise BusinessException(
                f"Work item has unexpected status {status!r} without replay authorization",
                action=self.name,
                halts_remaining_steps=True,
            )
        if fetched_hash != discovered_hash:
            raise BusinessException(
                "Work item changed since discovery",
                action=self.name,
                halts_remaining_steps=True,
            )
        ctx.state["validated"] = True
