from __future__ import annotations

import json

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from rpacore import BusinessException, ProcessContext, Step, SystemException

from steps._utils import REQUIRED_FIELDS, find_row_value as _find_row_value
from steps._utils import get_timeout, missing_required_fields

_FIELDS = REQUIRED_FIELDS


def _build_label_to_input_map(page) -> dict[str, str]:
    """Build a mapping from label text to input ID by querying rpa1-field components.

    The RPA Challenge form renders each field inside a <rpa1-field> Angular component.
    Labels are not programmatically linked to inputs (no <label for=""> or input.labels).
    We find the input inside the same component container as each label.
    """
    return page.evaluate(
        """() => {
            const containers = document.querySelectorAll('rpa1-field');
            const map = {};
            containers.forEach(c => {
                const label = c.querySelector('label');
                const input = c.querySelector('input');
                if (label && input) {
                    map[label.textContent.trim()] = input.id;
                }
            });
            return map;
        }"""
    )


def _fill_fields_via_js(page, label_map: dict[str, str], row: dict) -> None:
    """Fill form fields using JavaScript to set values and dispatch Angular events.

    The form uses Angular's change detection, so plain page.fill() doesn't trigger
    validation. We must set values directly and dispatch input/change/blur events.
    """
    data = {f: _find_row_value(row, f) for f in _FIELDS}
    data_json = json.dumps(data)
    label_map_json = json.dumps(label_map)
    js_code = """
        () => {
            const data = __DATA__;
            const map = __LABEL_MAP__;
            for (const [field, value] of Object.entries(data)) {
                const inputId = map[field];
                if (inputId) {
                    const input = document.getElementById(inputId);
                    input.value = value;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.dispatchEvent(new Event('blur', { bubbles: true }));
                }
            }
        }
    """.replace("__DATA__", data_json).replace("__LABEL_MAP__", label_map_json)
    page.evaluate(js_code)


class FillRow(Step):
    def execute(self, ctx: ProcessContext) -> None:
        page = ctx.resources["page"]
        row: dict = self.arguments["row"]

        missing = missing_required_fields(row)
        if missing:
            raise BusinessException(
                f"Row is missing required fields: {missing}",
                action=self.name,
                halts_remaining_steps=True,
            )

        try:
            label_map = _build_label_to_input_map(page)
            _fill_fields_via_js(page, label_map, row)
        except SystemException:
            raise
        except Exception as exc:
            raise SystemException(
                f"Failed to fill field in row: {exc}",
                action=self.name,
            ) from exc


class SubmitRow(Step):
    def execute(self, ctx: ProcessContext) -> None:
        page = ctx.resources["page"]

        try:
            # Click the submit INPUT inside the form (the button outside the form
            # does not trigger form submission in Angular).
            page.locator('form input[type="submit"]').click(
                timeout=get_timeout(ctx.config, "click")
            )
            # Wait for the page to transition to the next round or results.
            # The page shows "Round N" after a successful submission, or
            # "Congratulations" after the last round.
            # Use a two-phase check: first check for the congratulations message
            # (last row), then fall back to waiting for labels (intermediate rows).
            try:
                # Check if the congratulations message is on the page (last row)
                page.wait_for_selector(
                    ".congratulations",
                    timeout=get_timeout(ctx.config, "congratulations_check"),
                )
            except PlaywrightTimeoutError:
                # Not the last row — wait for the form to re-render with new labels
                # After each submission, the form fields are re-rendered with new IDs.
                page.wait_for_function(
                    """() => {
                        const labels = document.querySelectorAll('rpa1-field label');
                        if (labels.length < 2) return false;
                        return labels.length >= 2;
                    }""",
                    timeout=get_timeout(ctx.config, "form_transition"),
                )
        except Exception as exc:
            raise SystemException(
                f"Failed to submit row: {exc}",
                action=self.name,
            ) from exc
