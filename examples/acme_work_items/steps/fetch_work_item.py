from __future__ import annotations

from rpacore import ProcessContext, Step, SystemException

from steps._session import require_authenticated_session


class FetchWorkItem(Step):
    """Fetch a fresh durable snapshot of one remote ACME work item."""

    def execute(self, ctx: ProcessContext) -> None:
        work_item_id = ctx.require_state("work_item_id", str, action=self.name)
        try:
            item = require_authenticated_session(ctx).fetch_item(work_item_id)
        except SystemException:
            raise
        except Exception as exc:
            raise SystemException("Unable to fetch ACME work item", action=self.name) from exc

        ctx.state.update(
            {
                "client_id": item.client_id,
                "wiid": item.wiid,
                "fetched_type": item.item_type,
                "fetched_status": item.status,
                "fetched_hash": item.fingerprint,
            }
        )
