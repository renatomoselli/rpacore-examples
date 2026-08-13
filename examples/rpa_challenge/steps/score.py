from __future__ import annotations

import re

from rpacore import ProcessContext, Step, SystemException

from steps._utils import get_timeout


class RecordScore(Step):
    def execute(self, ctx: ProcessContext) -> None:
        page = ctx.resources["page"]
        try:
            # Wait for the results page to appear ("Congratulations" message)
            # The results page shows a .congratulations div after all 10 rounds are complete.
            # Use the specific CSS class selector — more reliable than checking body text,
            # which may not be rendered yet by Angular's change detection.
            page.wait_for_selector(".congratulations", timeout=get_timeout(ctx.config, "score_extraction"))

            # Get the full page text directly
            body_text = page.text_content("body")

            score_match = re.search(
                r"success rate is (\d+(?:\.\d+)?)%?", body_text, re.IGNORECASE
            )
            if score_match:
                ctx.state["score"] = f"{score_match.group(1)}%"
            else:
                # Fallback: extract a percent from alternate congratulations copy.
                congrats_match = re.search(
                    r"Congratulations!.*?(\d+(?:\.\d+)?)%?",
                    body_text,
                    re.IGNORECASE | re.DOTALL,
                )
                if not congrats_match:
                    raise SystemException(
                        "Final page did not contain a parseable score or congratulations message.",
                        action=self.name,
                    )
                ctx.state["score"] = f"{congrats_match.group(1)}%"
        except Exception as exc:
            raise SystemException(
                f"Failed to read final score: {exc}",
                action=self.name,
            ) from exc
