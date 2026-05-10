from __future__ import annotations
from oref import BusinessException, ProcessContext, Skill, SystemException

_FIELDS = [
    "First Name",
    "Last Name",
    "Company Name",
    "Role in Company",
    "Address",
    "Email",
    "Phone Number",
]


def _find_row_value(row: dict, field: str) -> str:
    """Look up a field value case-insensitively for robustness against Excel header changes."""
    lower = field.lower()
    for key, val in row.items():
        if str(key).strip().lower() == lower:
            return str(val or "")
    return ""


class FillRow(Skill):
    def execute(self, ctx: ProcessContext) -> None:
        page = ctx.data["page"]
        row: dict = self.arguments["row"]

        missing = [f for f in _FIELDS if not _find_row_value(row, f).strip()]
        if missing:
            raise BusinessException(
                f"Row is missing required fields: {missing}",
                action=self.name,
            )

        try:
            for field in _FIELDS:
                value = _find_row_value(row, field)
                page.get_by_label(field).fill(value, timeout=10_000)
        except Exception as exc:
            raise SystemException(
                f"Failed to fill field in row: {exc}",
                action=self.name,
            ) from exc


class SubmitRow(Skill):
    def execute(self, ctx: ProcessContext) -> None:
        page = ctx.data["page"]
        try:
            page.get_by_role("button", name="Submit").click(timeout=10_000)
            # Brief pause for the page to re-render the next form row.
            # (playwright-cli codegen recommended this; wait_for_timeout is
            #  deprecated but the site animates the form swap and needs a
            #  short delay — no network idle to wait for since the URL never changes.)
            page.wait_for_timeout(500)
        except Exception as exc:
            raise SystemException(
                f"Failed to submit row: {exc}",
                action=self.name,
            ) from exc
