"""Parse extracted PDF text into structured invoice data."""

from __future__ import annotations

import logging
import re
from datetime import datetime, date
from typing import Any

from oref import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)


class ParseInvoice(Skill):
    """Parse invoice text into structured data."""

    # Common invoice number patterns
    # Requires a separator (colon or hash) after the label to avoid
    # matching "INVOICE\nInvoice Number: INV-001" and capturing "Invoice"
    _INVOICE_RE = re.compile(
        r"(?:invoice|inv\.?|#|num\.?)\s*(?:no\.?|number|n\.)?\s*[:#]\s*"
        r"([A-Z0-9][A-Z0-9\-_.]+)",
        re.IGNORECASE,
    )

    # Common date patterns
    _DATE_RE = re.compile(
        r"\b(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})\b"
    )

    # Common vendor patterns — preserves original casing from the PDF text
    _VENDOR_RE = re.compile(
        r"(?:from|bill\s*from|vendor|company|issued\s*by)\s*[:#]?\s*"
        r"(.+?)(?:\n|$)",
        re.IGNORECASE,
    )

    # Total patterns — uses "net total" instead of "net " to avoid
    # matching "net income", "net profit", etc.
    # Negative lookbehind (?<![a-z]) prevents matching "Subtotal"
    _TOTAL_RE = re.compile(
        r"(?<![a-z])(?:total|amount\s*due|grand\s*total|net\s*total)\s*(?:amount)?\s*[:#]?\s*"
        r"([€$£¥R]?[€$£¥]?\s*[\d,]+\.?\d*)",
        re.IGNORECASE,
    )

    # Subtotal patterns
    _SUBTOTAL_RE = re.compile(
        r"(?:subtotal|sub\s*total)\s*(?:amount)?\s*[:#]?\s*"
        r"([€$£¥R]?[€$£¥]?\s*[\d,]+\.?\d*)",
        re.IGNORECASE,
    )

    def execute(self, ctx: ProcessContext) -> None:
        """Parse invoice text into structured data."""
        pdf_text = ctx.data.get("pdf_text", "")
        if not pdf_text:
            raise SystemException("No PDF text to parse", action=self.name)

        parsed: dict[str, Any] = {}

        # Extract invoice number
        inv_match = self._INVOICE_RE.search(pdf_text)
        parsed["invoice_number"] = inv_match.group(1).strip() if inv_match else ""

        # Extract date
        date_match = self._DATE_RE.search(pdf_text)
        if date_match:
            raw_date = date_match.group(1)
            parsed["date"] = self._normalize_date(raw_date)
        else:
            parsed["date"] = ""

        # Extract vendor
        vendor_match = self._VENDOR_RE.search(pdf_text)
        parsed["vendor"] = vendor_match.group(1).strip() if vendor_match else ""

        # Extract line items (skip lines that look like totals/summary)
        parsed["line_items"] = self._extract_line_items(pdf_text)

        # Extract total
        total_match = self._TOTAL_RE.search(pdf_text)
        parsed["total"] = total_match.group(1).strip() if total_match else ""

        # Extract subtotal (if present)
        subtotal_match = self._SUBTOTAL_RE.search(pdf_text)
        parsed["subtotal"] = subtotal_match.group(1).strip() if subtotal_match else ""

        # Detect currency from total
        parsed["currency"] = self._detect_currency(pdf_text)

        ctx.data["parsed_invoice"] = parsed
        logger.info("Parsed invoice: %s", parsed.get("invoice_number", "UNKNOWN"))

    def _normalize_date(self, raw: str) -> str:
        """Normalize a date string to ISO 8601 format.

        For slash-separated dates (DD/MM/YYYY or MM/DD/YYYY), the first
        interpretation that yields a valid date is used.

        For dash-separated dates (DD-MM-YYYY or MM-DD-YYYY), EU order
        (day-first) is tried before US order (month-first) to match
        common international invoice conventions.
        """
        raw = raw.strip()
        sep = raw[2] if len(raw) > 2 else "-"

        if sep == "/":
            # Slash-separated: try DD/MM/YYYY first, then MM/DD/YYYY
            for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d/%m/%y", "%m/%d/%y"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
        else:
            # Dash-separated: try EU (day-first) before US (month-first)
            for fmt in ("%d-%m-%Y", "%m-%d-%Y", "%d-%m-%y", "%m-%d-%y"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue

        # Already ISO 8601 or standard format
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return raw

    def _extract_line_items(self, text: str) -> list[dict[str, Any]]:
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
        """Check if a line looks like a summary/total line rather than a line item.

        Uses word-boundary matching to avoid filtering legitimate line items
        whose descriptions contain keywords like "total" (e.g. "Total Care Plan 3").
        """
        line_lower = line.lower()
        # Match keywords only at word boundaries (start or preceded by non-alpha)
        _SUMMARY_KEYWORDS = ["total", "subtotal", "amount due", "grand total", "net total"]
        for kw in _SUMMARY_KEYWORDS:
            idx = line_lower.find(kw)
            if idx == -1:
                continue
            # Check word boundary: keyword must be at start or preceded by non-alpha
            if idx > 0 and line_lower[idx - 1].isalpha():
                continue
            # Check word boundary: keyword must be at end or followed by non-alpha
            end = idx + len(kw)
            if end < len(line_lower) and line_lower[end].isalpha():
                continue
            return True
        return False

    @staticmethod
    def _try_parse_line_item(line: str) -> dict[str, Any] | None:
        """Try to parse a single line as a line item.

        Strategy:
        1. Tab-separated: split on tabs, last 2 tokens are qty/price.
        2. Double-space split: last token is price, second-to-last is qty.
        3. Fallback: find the last two numeric tokens from the right.
        """
        # Try tab-separated first (most reliable)
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
            if len(parts) >= 3:
                desc = parts[0]
                try:
                    qty = float(parts[1])
                    price_str = parts[2].replace("$", "").replace("€", "").replace("£", "").replace("¥", "").replace("R", "").strip()
                    price = float(price_str)
                    return {
                        "description": desc,
                        "quantity": qty,
                        "unit_price": round(price, 2),
                    }
                except (ValueError, IndexError):
                    pass

        # Try double-space or multi-space split
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 3:
            # Last token is price, second-to-last is quantity
            try:
                price = ParseInvoice._try_parse_number(parts[-1])
                qty = ParseInvoice._try_parse_number(parts[-2])
                if price is not None and qty is not None:
                    desc = " ".join(parts[:-2])
                    return {
                        "description": desc,
                        "quantity": qty,
                        "unit_price": round(price, 2),
                    }
            except (ValueError, TypeError):
                pass

        # Fallback: walk from the right to find two numeric tokens
        # The rightmost numeric token is the price, the one to its left is quantity
        tokens = line.split()
        if len(tokens) >= 3:
            numeric_from_right: list[tuple[int, float]] = []
            for i in range(len(tokens) - 1, -1, -1):
                num = ParseInvoice._try_parse_number(tokens[i])
                if num is not None:
                    numeric_from_right.append((i, num))
                    if len(numeric_from_right) == 2:
                        break

            if len(numeric_from_right) == 2:
                # First found (rightmost) = price, second found (left of it) = quantity
                price_idx, price = numeric_from_right[0]
                qty_idx, qty = numeric_from_right[1]
                if qty_idx < price_idx:
                    desc = " ".join(tokens[:qty_idx]).strip()
                    if desc:
                        return {
                            "description": desc,
                            "quantity": qty,
                            "unit_price": round(price, 2),
                        }

        return None

    @staticmethod
    def _try_parse_number(s: str) -> float | None:
        """Try to parse a string as a number, stripping currency symbols."""
        cleaned = s.strip()
        for symbol in ["R$", "$", "€", "£", "¥", "R"]:
            cleaned = cleaned.replace(symbol, "")
        cleaned = cleaned.replace(",", "")
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _detect_currency(text: str) -> str:
        """Detect currency symbol from invoice text.

        Scans the total string first (most reliable), then falls back
        to scanning specific invoice regions (total line, vendor block)
        rather than the entire document to avoid false positives from
        currency symbols in vendor names or descriptions.
        """
        # Try to detect from the total value first
        total_match = ParseInvoice._TOTAL_RE.search(text)
        if total_match:
            total_str = total_match.group(1)
            # Check R$ before $ to avoid false positive
            for symbol in ["€", "£", "¥", "R$", "$"]:
                if symbol in total_str:
                    if symbol == "R$":
                        return "BRL"
                    return symbol

        # Fallback: scan specific invoice regions, not the entire document
        for line in text.split("\n"):
            line_lower = line.lower().strip()
            if any(kw in line_lower for kw in [
                "total", "amount due", "grand total", "net total",
            ]):
                for symbol in ["€", "$", "£", "¥", "R$"]:
                    if symbol in line:
                        if symbol == "R$":
                            return "BRL"
                        return symbol

        return "USD"
