"""Fix parse_invoice.py bugs."""
import re

with open('skills/parse_invoice.py', 'r') as f:
    content = f.read()

# Fix 1: Change \s* to \s+ in _INVOICE_RE (require at least one whitespace after label)
old_invoice = r'''    _INVOICE_RE = re.compile(
        r"(?:invoice|inv\.?|#|num\.?)\s*(?:no\.?|number|n\.)?\s*[:#]?\s*"
        r"([A-Z0-9][A-Z0-9\-_.]+)",
        re.IGNORECASE,
    )'''

new_invoice = r'''    _INVOICE_RE = re.compile(
        r"(?:invoice|inv\.?|#|num\.?)\s+(?:no\.?|number|n\.)?\s*[:#]?\s*"
        r"([A-Z0-9][A-Z0-9\-_.]+)",
        re.IGNORECASE,
    )'''

if old_invoice in content:
    content = content.replace(old_invoice, new_invoice)
    print("Fix 1 applied: _INVOICE_RE \\s* -> \\s+")
else:
    print("Fix 1: old text not found")
    # Debug: show what's actually there
    idx = content.find('_INVOICE_RE')
    if idx >= 0:
        print(repr(content[idx:idx+200]))

# Fix 2: Add _is_summary_line method and update _extract_line_items
old_extract = r'''    def _extract_line_items(self, text: str) -> list[dict[str, Any]]:
        """Extract line items from invoice text.

        Uses position-based heuristics: the last numeric token is the price,
        the second-to-last is the quantity, and everything before is the
        description. This avoids corrupting descriptions that contain numbers
        (e.g. "Model 3 Adapter 10 $15.00").
        """
        items: list[dict[str, Any]] = []

        for line in text.split("\n"):
            line = line.strip()
            if not line or len(line) < 10:
                continue

            item = self._try_parse_line_item(line)
            if item:
                items.append(item)

        return items'''

new_extract = r'''    def _extract_line_items(self, text: str) -> list[dict[str, Any]]:
        """Extract line items from invoice text.

        Uses position-based heuristics: the last numeric token is the price,
        the second-to-last is the quantity, and everything before is the
        description. This avoids corrupting descriptions that contain numbers
        (e.g. "Model 3 Adapter 10 $15.00").

        Skips lines that look like totals, subtotals, or headers.
        """
        items: list[dict[str, Any]] = []

        for line in text.split("\n"):
            line = line.strip()
            if not line or len(line) < 10:
                continue

            # Skip lines that look like totals/summary/headers
            if self._is_summary_line(line):
                continue

            item = self._try_parse_line_item(line)
            if item:
                items.append(item)

        return items

    @staticmethod
    def _is_summary_line(line: str) -> bool:
        """Check if a line looks like a summary/total line rather than a line item."""
        line_lower = line.lower()
        return any(
            kw in line_lower
            for kw in ["total", "subtotal", "amount due", "grand total", "net total"]
        )'''

if old_extract in content:
    content = content.replace(old_extract, new_extract)
    print("Fix 2 applied: _is_summary_line added")
else:
    print("Fix 2: old text not found")

with open('skills/parse_invoice.py', 'w') as f:
    f.write(content)

print("Done!")
