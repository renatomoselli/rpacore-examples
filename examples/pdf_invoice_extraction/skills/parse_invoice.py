"""Parse extracted PDF text into structured invoice data."""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime
from typing import Any

from rpacore import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)

_MAX_INVOICE_NUMBER_LENGTH = 64
_MAX_VENDOR_LENGTH = 120
_MAX_MONEY_LENGTH = 32
_MAX_CURRENCY_LENGTH = 8
_MAX_DESCRIPTION_LENGTH = 160

class ParseInvoice(Skill):
    """Parse invoice text into structured data."""

    # Common invoice number patterns
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

    # Total patterns
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

    # Some PDF extractors can surface ReportLab-rendered tabs as literal "n"
    # glyphs. Keep this fallback narrow so ordinary words containing "n" are
    # not treated as column separators.
    # The mojibake currency literals match double-encoded PDF text extraction.
    _COMPACT_LINE_ITEM_RE = re.compile(
        r"^(?P<desc>.+?)n(?P<qty>\d+(?:\.\d+)?)n"
        r"(?P<price>R?\$|â‚¬|Â£|Â¥)?\s*(?P<amount>[\d,]+(?:\.\d+)?)$"
    )

    def execute(self, ctx: ProcessContext) -> None:
        """Parse invoice text into structured data."""
        pdf_text = ctx.optional_state("pdf_text", str, "", action=self.name)
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

        parsed = self._sanitize_parsed_invoice(parsed)
        ctx.state["parsed_invoice"] = parsed
        logger.info("Parsed invoice: %s", parsed.get("invoice_number", "UNKNOWN"))

    def _sanitize_parsed_invoice(self, parsed: dict[str, Any]) -> dict[str, Any]:
        """Sanitize parsed invoice data before it enters durable state."""
        sanitized = dict(parsed)
        sanitized["invoice_number"] = self._clean_text(
            sanitized.get("invoice_number", ""), max_length=_MAX_INVOICE_NUMBER_LENGTH
        )
        sanitized["date"] = self._clean_text(sanitized.get("date", ""), max_length=32)
        sanitized["vendor"] = self._clean_text(
            sanitized.get("vendor", ""), max_length=_MAX_VENDOR_LENGTH
        )
        sanitized["total"] = self._clean_money(sanitized.get("total", ""), "total")
        sanitized["subtotal"] = self._clean_money(sanitized.get("subtotal", ""), "subtotal")
        sanitized["currency"] = self._clean_text(
            sanitized.get("currency", "USD"), max_length=_MAX_CURRENCY_LENGTH
        )

        line_items = sanitized.get("line_items", [])
        if not isinstance(line_items, list):
            raise SystemException("Parsed line_items must be a list", action=self.name)
        sanitized["line_items"] = [
            self._sanitize_line_item(item)
            for item in line_items
            if isinstance(item, dict)
        ]
        return sanitized

    def _sanitize_line_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Sanitize one parsed line item for durable state."""
        quantity = item.get("quantity", 0)
        unit_price = item.get("unit_price", 0)
        try:
            quantity = float(quantity)
            unit_price = float(unit_price)
        except (TypeError, ValueError) as exc:
            raise SystemException(
                f"Invalid line item numeric value: {item!r}",
                action=self.name,
            ) from exc
        return {
            "description": self._clean_text(
                item.get("description", ""), max_length=_MAX_DESCRIPTION_LENGTH
            ),
            "quantity": quantity,
            "unit_price": round(unit_price, 2),
        }

    def _clean_money(self, value: object, field_name: str) -> str:
        """Clean a captured money string and verify it remains parseable."""
        text = self._clean_text(value, max_length=_MAX_MONEY_LENGTH)
        if text and ParseInvoice._try_parse_number(text) is None:
            raise SystemException(
                f"Parsed {field_name} is not numeric: {text!r}",
                action=self.name,
            )
        return text

    @staticmethod
    def _clean_text(value: object, *, max_length: int) -> str:
        """Strip control characters and bound string length."""
        text = "" if value is None else str(value)
        text = "".join(
            " " if unicodedata.category(char) == "Cc" else char
            for char in text
        )
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_length]

    def _normalize_date(self, raw: str) -> str:
        """Normalize a date string to ISO 8601 format."""
        raw = raw.strip()
        sep = raw[2] if len(raw) > 2 else "-"

        if sep == "/":
            for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d/%m/%y", "%m/%d/%y"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
        else:
            for fmt in ("%d-%m-%Y", "%m-%d-%Y", "%d-%m-%y", "%m-%d-%y"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue

        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return raw

    def _extract_line_items(self, text: str) -> list[dict[str, Any]]:
        """Extract line items from invoice text."""
        items: list[dict[str, Any]] = []

        for line in text.split("\n"):
            line = line.strip()
            if not line or len(line) < 10:
                continue

            if self._is_summary_line(line):
                continue

            item = self._try_parse_line_item(line)
            if item:
                items.append(item)

        return items

    @staticmethod
    def _is_summary_line(line: str) -> bool:
        """Check if a line looks like a summary/total line."""
        line_lower = line.lower()
        _SUMMARY_KEYWORDS = ["total", "subtotal", "amount due", "grand total", "net total"]
        for kw in _SUMMARY_KEYWORDS:
            idx = line_lower.find(kw)
            if idx == -1:
                continue
            if idx > 0 and line_lower[idx - 1].isalpha():
                continue
            end = idx + len(kw)
            if end < len(line_lower) and line_lower[end].isalpha():
                continue
            return True
        return False

    @staticmethod
    def _try_parse_line_item(line: str) -> dict[str, Any] | None:
        """Try to parse a single line as a line item."""
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

        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 3:
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

        compact_item = ParseInvoice._try_parse_compact_line_item(line)
        if compact_item is not None:
            return compact_item

        return None

    @staticmethod
    def _try_parse_compact_line_item(line: str) -> dict[str, Any] | None:
        """Parse line items where PDF extraction collapsed tabs into 'n' glyphs."""
        match = ParseInvoice._COMPACT_LINE_ITEM_RE.match(line.strip())
        if match is None:
            return None

        desc = match.group("desc").strip()
        qty = ParseInvoice._try_parse_number(match.group("qty"))
        price = ParseInvoice._try_parse_number(
            f"{match.group('price') or ''}{match.group('amount')}"
        )
        if not desc or qty is None or price is None:
            return None

        return {
            "description": desc,
            "quantity": qty,
            "unit_price": round(price, 2),
        }

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
        """Detect currency symbol from invoice text."""
        total_match = ParseInvoice._TOTAL_RE.search(text)
        if total_match:
            total_str = total_match.group(1)
            for symbol in ["€", "£", "¥", "R$", "$"]:
                if symbol in total_str:
                    if symbol == "R$":
                        return "BRL"
                    return symbol

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
