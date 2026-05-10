from __future__ import annotations
import os
import tempfile
import urllib.request
from pathlib import Path
import openpyxl
from playwright.sync_api import sync_playwright
from oref import BusinessException, ProcessContext, Skill, SystemException

# Default URL - can be overridden via config
DEFAULT_XLSX_URL = "https://www.rpachallenge.com/assets/downloadFiles/challenge.xlsx"

# Selectors verified via: playwright-cli snapshot
#   open https://www.rpachallenge.com --headed
#   playwright-cli snapshot
#   click Start ref
#   playwright-cli snapshot


class OpenChallengePage(Skill):
    def execute(self, ctx: ProcessContext) -> None:
        max_page_load_retries = int(str(ctx.config.get("max_page_load_retries", 3)))
        
        for attempt in range(1, max_page_load_retries + 1):
            page = None
            try:
                pw = sync_playwright().start()
                try:
                    browser = pw.chromium.launch(headless=False)
                except Exception:
                    raise SystemException(
                        "Chrome headless launch failed — this machine may lack a display. "
                        "Install Chrome/Chromium or set credential_provider for headless mode.",
                        action=self.name,
                    )
                page = browser.new_page()
                page.goto("https://www.rpachallenge.com/", timeout=30_000)
                # Wait for page to fully load (important for SPA with dynamic content)
                page.wait_for_load_state("networkidle")
                ctx.data["_pw"] = pw  # Store Playwright instance for cleanup in RecordScore
                ctx.data["page"] = page  # Store page for use by other skills
                return  # Success
            except Exception as exc:
                if attempt == max_page_load_retries:
                    raise SystemException(
                        f"Failed to load page after {max_page_load_retries} attempts: {exc}",
                        action=self.name,
                    )
                # Log retry attempt
                print(f"Page load attempt {attempt}/{max_page_load_retries} failed: {exc}")
                # Brief delay before retry to allow any transient issues to resolve
                if page is not None:
                    page.wait_for_timeout(2_000)


class DownloadInputData(Skill):
    def execute(self, ctx: ProcessContext) -> None:
        # Use configurable URL from config, fall back to default
        xlsx_url = str(ctx.config.get("xlsx_url", DEFAULT_XLSX_URL))
        
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
        _closed = False

        def _cleanup():
            nonlocal _closed, tmp_fd
            if not _closed and tmp_fd is not None:
                try:
                    os.close(tmp_fd)
                except OSError:
                    pass
                tmp_fd = None
                _closed = True
            Path(tmp_path).unlink(missing_ok=True)

        # Try direct download first
        try:
            urllib.request.urlretrieve(xlsx_url, tmp_path)
        except Exception:
            # Fallback: download via browser (site rate-limits direct requests)
            page = ctx.data["page"]
            page.click("a[role=\"link\"].cloud_download", timeout=10_000)
            page.wait_for_selector("a:has-text(\"Download Excel\")", state="detached", timeout=15_000)
            download = page.context.downloads[-1]
            Path(download.path).rename(tmp_path)
        
        try:
            wb = openpyxl.load_workbook(tmp_path)
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            headers = [str(h).strip() if h else "" for h in next(rows_iter)]
            rows = [dict(zip(headers, row)) for row in rows_iter if any(v for v in row)]
        except Exception as exc:
            _cleanup()
            raise SystemException(f"Failed to parse Excel file: {exc}", action=self.name) from exc
        
        if not rows:
            raise BusinessException("Input Excel file contains no data rows.", action=self.name)
        
        # Cleanup temporary file
        _cleanup()
        
        # Validate schema matches expected headers
        EXPECTED_HEADERS = {
            "first name", "last name", "company name", "role in company",
            "address", "email", "phone number"
        }
        actual_headers = {str(h).strip().lower() for h in headers}
        missing_headers = EXPECTED_HEADERS - actual_headers
        
        if missing_headers:
            raise SystemException(
                f"Excel missing expected headers: {missing_headers}",
                action=self.name,
            )


class StartChallenge(Skill):
    def execute(self, ctx: ProcessContext) -> None:
        page = ctx.data["page"]
        try:
            page.get_by_role("button", name="Start").click(timeout=10_000)
            # Wait for the download button to appear (it appears after Start)
            page.wait_for_selector("a[role=\"link\"].cloud_download", timeout=10_000)
        except Exception as exc:
            raise SystemException(
                f"Failed to start the challenge: {exc}",
                action=self.name,
            ) from exc
