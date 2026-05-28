from __future__ import annotations

import time
import re

from oref import ProcessContext, Skill, SystemException

from skills._utils import get_timeout


class RecordScore(Skill):
    def execute(self, ctx: ProcessContext) -> None:
        page = ctx.data["page"]
        try:
            # Brief pause for the page to finish updating after the last submission.
            time.sleep(2)

            # Wait for the results page to appear ("Congratulations" message)
            # The results page shows a .congratulations div after all 10 rounds are complete.
            # Use the specific CSS class selector — more reliable than checking body text,
            # which may not be rendered yet by Angular's change detection.
            page.wait_for_selector(".congratulations", timeout=get_timeout(ctx.config, "score_extraction"))

            # Get the full page text directly
            body_text = page.text_content("body")

            score_match = re.search(
                r"success rate is ([\d.]+)%", body_text, re.IGNORECASE
            )
            if score_match:
                ctx.data["score"] = f"{score_match.group(1)}%"
            else:
                # Fallback: capture the full congratulations message
                congrats_match = re.search(
                    r"Congratulations!([^.]*\.\s*)", body_text, re.IGNORECASE
                )
                ctx.data["score"] = (
                    congrats_match.group(0).strip()
                    if congrats_match
                    else "unknown"
                )
        except Exception as exc:
            raise SystemException(
                f"Failed to read final score: {exc}",
                action=self.name,
            ) from exc
