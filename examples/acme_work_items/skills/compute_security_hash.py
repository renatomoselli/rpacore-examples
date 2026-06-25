from __future__ import annotations

import hashlib

from rpacore import ProcessContext, Skill, SystemException

from skills._session import compute_identity_hash


class ComputeSecurityHash(Skill):
    """Compute and persist the deterministic intent before remote mutation."""

    def execute(self, ctx: ProcessContext) -> None:
        validated = ctx.require_state("validated", bool, action=self.name)
        if not validated:
            raise SystemException("Validated state is required", action=self.name)
        client_id = ctx.require_state("client_id", str, action=self.name)
        wiid = ctx.require_state("wiid", str, action=self.name)
        work_item_id = ctx.require_state("work_item_id", str, action=self.name)
        discovered_hash = ctx.require_state("discovered_hash", str, action=self.name)

        security_hash = compute_identity_hash(client_id, wiid)
        intent_material = f"{work_item_id}|{discovered_hash}|{security_hash}"
        ctx.state["security_hash"] = security_hash
        ctx.state["update_intent_id"] = hashlib.sha256(
            intent_material.encode("utf-8")
        ).hexdigest()
