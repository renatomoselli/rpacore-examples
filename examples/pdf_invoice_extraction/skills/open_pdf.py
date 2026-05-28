"""Open a PDF file and extract text using pdfplumber."""

from __future__ import annotations

import logging

from oref import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)


class OpenPdf(Skill):
    """Open a PDF file and extract all text content.

    Expected input keys in ctx.data:
        - file_path: str — Path to the PDF file

    Sets on ctx.data:
        - pdf_text: str — Extracted text from the PDF
    """

    def execute(self, ctx: ProcessContext) -> None:
        file_path = ctx.data.get("file_path")
        if file_path is None:
            raise SystemException(
                "No file_path in context — scan_inbox must run first",
                action=self.name,
            )

        try:
            import pdfplumber

            max_pages = int(ctx.config.get("max_pages", 100))

            with pdfplumber.open(file_path) as pdf:
                page_count = min(len(pdf.pages), max_pages)
                text_parts: list[str] = []
                for i, page in enumerate(pdf.pages[:page_count]):
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

                ctx.data["pdf_text"] = "\n".join(text_parts)
                ctx.data["pdf_pages"] = page_count

        except FileNotFoundError as exc:
            raise SystemException(
                f"PDF file not found: {file_path}",
                action=self.name,
            ) from exc
        except PermissionError as exc:
            raise SystemException(
                f"Permission denied reading PDF: {file_path}",
                action=self.name,
            ) from exc
        except Exception as exc:
            raise SystemException(
                f"Failed to open PDF {file_path}: {exc}",
                action=self.name,
            ) from exc

        logger.info(
            "Opened PDF: %s (%d pages, %d characters)",
            file_path,
            ctx.data.get("pdf_pages", 0),
            len(ctx.data.get("pdf_text", "")),
        )
