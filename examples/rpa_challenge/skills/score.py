from __future__ import annotations
from oref import ProcessContext, Skill, SystemException


class RecordScore(Skill):
    def execute(self, ctx: ProcessContext) -> None:
        page = ctx.data["page"]
        try:
            # The challenge shows a score block after the final submission.
            # Selector verified via: playwright-cli snapshot after last submit.
            score_locator = page.locator(".message2")
            score_locator.wait_for(timeout=10_000)
            score_text = score_locator.inner_text()
        except Exception as exc:
            raise SystemException(
                f"Failed to read final score: {exc}",
                action=self.name,
            ) from exc
        finally:
            try:
                ctx.data["_pw"].stop()
            except Exception:
                pass

        ctx.data["score"] = score_text.strip()
