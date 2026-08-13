from __future__ import annotations
import ipaddress
import os
import random
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
import openpyxl
from playwright.sync_api import sync_playwright
from rpacore import ProcessContext, Step, SystemException

from steps._utils import REQUIRED_FIELDS, get_timeout, missing_required_fields

# Default URL - can be overridden via config
DEFAULT_XLSX_URL = "https://www.rpachallenge.com/assets/downloadFiles/challenge.xlsx"
DEFAULT_XLSX_ALLOWED_HOSTS = {"www.rpachallenge.com"}
_ALLOWED_URL_SCHEMES = {"http", "https"}

# Selectors verified via: playwright-cli snapshot
#   open https://www.rpachallenge.com --headed
#   playwright-cli snapshot


def _allowed_hosts_from_config(config: dict) -> set[str]:
    hosts = config.get("xlsx_allowed_hosts", sorted(DEFAULT_XLSX_ALLOWED_HOSTS))
    if isinstance(hosts, str):
        return {hosts.lower()}
    if isinstance(hosts, list) and all(isinstance(host, str) for host in hosts):
        return {host.lower() for host in hosts}
    raise SystemException(
        "xlsx_allowed_hosts must be a string or list of strings",
        action="download_input_data",
    )


def _positive_int_from_config(config: dict, key: str, default: int, action: str) -> int:
    raw_value = config.get(key, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise SystemException(
            f"Config key '{key}' must be an integer, got {raw_value!r}",
            action=action,
        ) from exc
    if value < 1:
        raise SystemException(
            f"Config key '{key}' must be >= 1, got {value}",
            action=action,
        )
    return value


def _validate_xlsx_url(url: str, allowed_hosts: set[str] | None = None) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in _ALLOWED_URL_SCHEMES or not parsed.hostname:
        raise SystemException(
            f"xlsx_url must be an HTTP(S) URL with a host, got {url!r}",
            action="download_input_data",
        )

    allowed_hosts = DEFAULT_XLSX_ALLOWED_HOSTS if allowed_hosts is None else allowed_hosts
    hostname = parsed.hostname.lower()
    # Exact match only. Do not broaden this to suffix matching without a DNS trust review.
    if hostname not in allowed_hosts:
        raise SystemException(
            f"xlsx_url host must be one of {sorted(allowed_hosts)}, got {parsed.hostname!r}",
            action="download_input_data",
        )

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return url

    if address.is_private or address.is_loopback or address.is_link_local:
        raise SystemException(
            f"xlsx_url host must not be a private, loopback, or link-local IP address: {hostname}",
            action="download_input_data",
        )
    return url
#   click Start ref
#   playwright-cli snapshot


class OpenChallengePage(Step):
    def execute(self, ctx: ProcessContext) -> None:
        max_page_load_retries = _positive_int_from_config(
            ctx.config,
            "max_page_load_retries",
            3,
            self.name,
        )
        
        for attempt in range(1, max_page_load_retries + 1):
            pw = None
            page = None
            try:
                pw = sync_playwright().start()
                try:
                    headless = str(ctx.config.get("headless", "true")).lower() == "true"
                    browser = pw.chromium.launch(headless=headless)
                except Exception as exc:
                    raise SystemException(
                        "Chrome launch failed — this machine may lack a display. "
                        "Ensure Chrome/Chromium is installed or set headless=true in config.",
                        action=self.name,
                    ) from exc
                page = browser.new_page()
                page.goto("https://www.rpachallenge.com/", timeout=get_timeout(ctx.config, "page_load"))
                page.wait_for_load_state("networkidle")
                ctx.resources["_pw"] = pw
                ctx.resources["page"] = page
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
                    ) from exc
                print(f"Page load attempt {attempt}/{max_page_load_retries} failed: {exc}")
                # Brief pause before retry, with jitter to avoid synchronized retries.
                time.sleep(0.5 + random.random() * 0.5)


class DownloadInputData(Step):
    def execute(self, ctx: ProcessContext) -> None:
        # Use configurable URL from config, fall back to default
        xlsx_url = _validate_xlsx_url(
            str(ctx.config.get("xlsx_url", DEFAULT_XLSX_URL)),
            _allowed_hosts_from_config(ctx.config),
        )
        
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
        except (urllib.error.URLError, OSError):
            # Fallback: download via browser (site rate-limits direct requests)
            page = ctx.resources.get("page")
            if page is None:
                _cleanup()
                raise SystemException(
                    "Browser download fallback requires a page resource.",
                    action=self.name,
                )
            try:
                with page.expect_download() as dl_info:
                    page.click('a:has-text("Download Excel")', timeout=get_timeout(ctx.config, "click"))
                download = dl_info.value
                download.save_as(tmp_path)
            except Exception as exc:
                _cleanup()
                raise SystemException(f"Failed to download Excel file: {exc}", action=self.name) from exc
        
        try:
            wb = openpyxl.load_workbook(tmp_path)
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            try:
                header_row = next(rows_iter)
            except StopIteration:
                _cleanup()
                raise SystemException("Input Excel file is empty (no headers).", action=self.name)
            headers = [str(h).strip() if h else "" for h in header_row]
            rows = [dict(zip(headers, row)) for row in rows_iter if any(v is not None for v in row)]
        except SystemException:
            raise
        except Exception as exc:
            _cleanup()
            raise SystemException(f"Failed to parse Excel file: {exc}", action=self.name) from exc
        
        # Validate schema matches expected headers
        actual_headers = {str(h).strip().lower() for h in headers}
        missing_headers = {field.lower() for field in REQUIRED_FIELDS} - actual_headers

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
            missing_values = missing_required_fields(row)
            if missing_values:
                _cleanup()
                raise SystemException(
                    f"Excel row {row_index} missing required value(s): {sorted(missing_values)}",
                    action=self.name,
                )

        # Cleanup temporary file
        _cleanup()

        ctx.state["rows"] = rows


class StartChallenge(Step):
    def execute(self, ctx: ProcessContext) -> None:
        page = ctx.resources["page"]
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
