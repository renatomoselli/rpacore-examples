from __future__ import annotations
import os
import tempfile
import time
import urllib.request
from pathlib import Path
import openpyxl
from playwright.sync_api import sync_playwright
from rpacore import ProcessContext, Skill, SystemException

from skills._utils import find_row_value as _find_row_value
from skills._utils import get_timeout

# Default URL - can be overridden via config
DEFAULT_XLSX_URL = "https://www.rpachallenge.com/assets/downloadFiles/challenge.xlsx"
EXPECTED_HEADERS = {
    "first name",
    "last name",
    "company name",
    "role in company",
    "address",
    "email",
    "phone number",
}

# Selectors verified via: playwright-cli snapshot
#   open https://www.rpachallenge.com --headed
#   playwright-cli snapshot
#   click Start ref
#   playwright-cli snapshot


class OpenChallengePage(Skill):
    def execute(self, ctx: ProcessContext) -> None:
        max_page_load_retries = int(str(ctx.config.get("max_page_load_retries", 3)))
        
        for attempt in range(1, max_page_load_retries + 1):
            pw = None
            page = None
            try:
                pw = sync_playwright().start()
                try:
                    headless = str(ctx.config.get("headless", "true")).lower() == "true"
                    browser = pw.chromium.launch(headless=headless)
                except Exception:
                    raise SystemException(
                        "Chrome launch failed — this machine may lack a display. "
                        "Ensure Chrome/Chromium is installed or set headless=true in config.",
                        action=self.name,
                    )
                page = browser.new_page()
                page.goto("https://www.rpachallenge.com/", timeout=get_timeout(ctx.config, "page_load"))
                page.wait_for_load_state("networkidle")
                ctx.data["_pw"] = pw
                ctx.data["page"] = page
                return
            except Exception as exc:
                if page is not None:
                    page.close()
                if pw is not None:
                    pw.stop()
                if attempt == max_page_load_retries:
                    raise SystemException(
                        f"Failed to load page after {max_page_load_retries} attempts: {exc}",
                        action=self.name,
                    )
                print(f"Page load attempt {attempt}/{max_page_load_retries} failed: {exc}")
                # Brief pause before retry
                time.sleep(0.5)


class DownloadInputData(Skill):
    def execute(self, ctx: ProcessContext) -> None:
        # Use configurable URL from config, fall back to default
        xlsx_url = str(ctx.config.get("xlsx_url", DEFAULT_XLSX_URL))
        
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
        # Close the fd immediately — urlretrieve writes to the path directly,
        # and leaving the fd open causes file-locking issues on Windows.
        try:
            os.close(tmp_fd)
        except OSError:
            pass
        tmp_fd = None

        def _cleanup():
            Path(tmp_path).unlink(missing_ok=True)

        # Try direct download first
        try:
            urllib.request.urlretrieve(xlsx_url, tmp_path)
        except Exception:
            # Fallback: download via browser (site rate-limits direct requests)
            page = ctx.data["page"]
            with page.expect_download() as dl_info:
                page.click('a:has-text("Download Excel")', timeout=get_timeout(ctx.config, "click"))
            download = dl_info.value
            download.save_as(tmp_path)
        
        try:
            wb = openpyxl.load_workbook(tmp_path)
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            headers = [str(h).strip() if h else "" for h in next(rows_iter)]
            rows = [dict(zip(headers, row)) for row in rows_iter if any(v for v in row)]
        except Exception as exc:
            _cleanup()
            raise SystemException(f"Failed to parse Excel file: {exc}", action=self.name) from exc
        
        # Validate schema matches expected headers
        actual_headers = {str(h).strip().lower() for h in headers}
        missing_headers = EXPECTED_HEADERS - actual_headers

        if missing_headers:
            _cleanup()
            raise SystemException(
                f"Excel missing expected headers: {missing_headers}",
                action=self.name,
            )

        if not rows:
            _cleanup()
            raise SystemException("Input Excel file contains no data rows.", action=self.name)

        for row_index, row in enumerate(rows, start=2):
            missing_values = [
                header
                for header in EXPECTED_HEADERS
                if not _find_row_value(row, header).strip()
            ]
            if missing_values:
                _cleanup()
                raise SystemException(
                    f"Excel row {row_index} missing required value(s): {sorted(missing_values)}",
                    action=self.name,
                )

        # Cleanup temporary file
        _cleanup()

        # Store parsed rows for downstream skills
        ctx.data["rows"] = rows


class StartChallenge(Skill):
    def execute(self, ctx: ProcessContext) -> None:
        page = ctx.data["page"]
        try:
            # Wait for the page to be fully loaded
            page.wait_for_load_state('networkidle')

            # Check if the START button is still on the page.
            # If the START button exists, we haven't started the challenge yet.
            # If it doesn't exist, the form is already visible — nothing to do.
            start_btn = page.query_selector('button:has-text("START")')
            if start_btn is None:
                # Form is already visible — nothing to do
                return

            # Click the START button — use a robust selector that survives DOM changes
            # The button text is "START" (case-insensitive in text, but exact in DOM)
            page.click('button:has-text("START")', timeout=get_timeout(ctx.config, "click"))

            # Wait for the form to appear by checking for rpa1-field components
            # After clicking START, the form fields are re-rendered with new IDs.
            page.wait_for_function(
                """() => {
                    const containers = document.querySelectorAll('rpa1-field');
                    return containers.length >= 5;
                }""",
                timeout=get_timeout(ctx.config, "form_transition"),
            )
        except Exception as exc:
            raise SystemException(
                f"Failed to start the challenge: {exc}",
                action=self.name,
            ) from exc

