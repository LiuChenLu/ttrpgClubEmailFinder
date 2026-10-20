"""Stage 3: repair blank or suspiciously short page text from Stage 2.

Reads filtered_candidates.csv and writes rendered_results.csv with the same
rows in the same order. Discarded rows pass through without rendering; kept
rows have their page text repaired in up to two steps:

  1. Blank text gets a Tavily extract(), retrying failures only.
  2. Text that is still blank, or that is non-blank but short on a .edu URL,
     is re-fetched by rendering the page in headless Chromium (Playwright).

Playwright text is plain text, not markdown, so hrefs hidden behind link text
(mailto:, Discord invites) are gone. content_source records where each row's
text came from, so later stages never have to guess its format.

When there are kept rows, Chromium is launched before the output file is opened
and before any API call. An all-discard input needs no browser startup.

Setup:
    pip install tavily-python python-dotenv playwright
    playwright install chromium
    Create .env with: TAVILY_API_KEY=tvly-... and TTRPG_DEBUG=0 or 1

Set TTRPG_DEBUG=1 in .env for per-row extract() and Playwright logging.
"""

from __future__ import annotations
from contextlib import nullcontext
from config import (
    EXTRACT_DEPTH, EXTRACT_MAX_ATTEMPTS, EXTRACT_RETRY_SLEEP_S,
    PLAYWRIGHT_MAX_CONSECUTIVE_CRASHES, PLAYWRIGHT_TIMEOUT_MS,
    RAW_CONTENT_FORMAT, DEFAULT_FILTERED_CSV, RENDERED_RESULTS_CSV,
    SHORT_CONTENT_CHARS,
)
from schema import RENDERED_NEW_FIELDNAMES, is_keep, rendered_fieldnames, require_columns
from search_row_format_util import is_sentinel, sanitize_for_csv
from stage_cli import build_parser
from tavily_client_util import tavily
from collections.abc import Sequence

import csv
import logging
import os
import re
import time


DEBUG = os.environ.get("TTRPG_DEBUG") == "1"

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("render_candidates")
logger.setLevel(logging.DEBUG if DEBUG else logging.WARNING)

# Columns Stage 2's output must have.
REQUIRED_INPUT_COLUMNS = [
    "decision",
    "result_url", "search_query", "raw_content_status",
    "raw_content_length", "result_raw_content",
]
# If the input already has any of the columns this stage adds, it is not a
# current Stage 2 output, and writing it back out would duplicate the column.
NEW_FIELDNAMES = RENDERED_NEW_FIELDNAMES

INSTALL_HINT = "Run `pip install playwright` and `playwright install chromium`."


class ExtractStatus:
    """Outcome of the Tavily extract(); the last attempt's result is kept.

    The column is blank, not a status, when extract wasn't attempted.
    """

    SUCCEEDED = "succeeded"
    SUCCEEDED_EMPTY = "succeeded_empty"
    FAILED_PER_URL = "failed_per_url"
    FAILED_EXCEPTION = "failed_exception"
    NO_RESPONSE_ENTRY = "no_response_entry"


# An extract that succeeds with empty text means the page itself is empty, so
# retrying it just burns calls. Only failures are worth another attempt.
RETRYABLE = {
    ExtractStatus.FAILED_PER_URL,
    ExtractStatus.FAILED_EXCEPTION,
    ExtractStatus.NO_RESPONSE_ENTRY,
}


class RenderStatus:
    """Outcome of the Playwright step; blank on sentinel rows."""

    NOT_NEEDED = "not_needed"      # Playwright wasn't triggered
    SUCCEEDED = "succeeded"        # returned non-empty text
    FAILED_PER_URL = "failed_per_url"  # raised, timed out, or returned nothing


class ContentSource:
    """Where a row's final result_raw_content came from; blank if it's blank."""

    SEARCH = "search"
    EXTRACT = "extract"
    PLAYWRIGHT = "playwright"


class RenderAbort(RuntimeError):
    """The browser is unusable, so carrying on would silently fail every
    remaining row. Rows already written stay flushed in the output."""


# A literal ".edu" anywhere in the URL, not a hostname check: the URL may or may
# not carry a scheme, and club pages sit under .edu subdomains
# (uconntact.uconn.edu). The lookahead stops ".edu" matching the start of
# another label (educause.org, education.com): it has to end the URL or be
# followed by one of  . / ? : #  . Known false positives, accepted because each
# only costs an unneeded Playwright run: .edu.cn / .edu.au hosts, and ".edu"
# inside a path or query string.
_EDU_URL_RE = re.compile(r"\.edu(?=$|[./?:#])", re.IGNORECASE)


def is_edu_url(url: str) -> bool:
    return _EDU_URL_RE.search(url.strip()) is not None


def is_blank(text: str) -> bool:
    return not text.strip()


def needs_playwright(content: str, url: str) -> bool:
    """Blank text always needs it; short non-blank text only on .edu URLs.

    Short stubs on other hosts (including many vendor-hosted club pages) are
    deliberately not detected: an arbitrary length cut-off applied to every
    host would send too many legitimately short pages through Playwright.
    """
    if is_blank(content):
        return True
    return len(content) < SHORT_CONTENT_CHARS and is_edu_url(url)


def extract_once(url: str) -> tuple[str, str]:
    """One extract() call for one URL. Returns (status, page text)."""
    try:
        response = tavily().extract(
            urls=[url], format=RAW_CONTENT_FORMAT, extract_depth=EXTRACT_DEPTH,
        )
    except Exception as e:
        logger.debug("extract() raised for %s: %s", url, e)
        return ExtractStatus.FAILED_EXCEPTION, ""

    # One URL per call, so any entry is ours. Tavily may normalise the URL it
    # echoes back, which is why we don't match on it.
    if response.get("results"):
        text = sanitize_for_csv(response["results"][0].get("raw_content") or "")
        if text.strip():
            return ExtractStatus.SUCCEEDED, text
        return ExtractStatus.SUCCEEDED_EMPTY, ""

    # Tavily reports per-URL failures here rather than raising.
    if response.get("failed_results"):
        error = response["failed_results"][0].get("error", "")
        logger.debug("extract() failed for %s: %s", url, error)
        return ExtractStatus.FAILED_PER_URL, ""

    return ExtractStatus.NO_RESPONSE_ENTRY, ""


def extract_with_retries(url: str) -> tuple[str, str]:
    """Up to EXTRACT_MAX_ATTEMPTS extract() calls, retrying failures only.

    Returns the last attempt's (status, page text). A failed extraction doesn't
    invalidate the row; the caller moves on to Playwright.
    """
    status, text = "", ""
    for attempt in range(EXTRACT_MAX_ATTEMPTS):
        if attempt:
            time.sleep(EXTRACT_RETRY_SLEEP_S)
        status, text = extract_once(url)
        if status not in RETRYABLE:
            break
    return status, text


def _default_playwright_factory():
    # Imported here so the rest of this module works (and is testable) without
    # the playwright package installed.
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RenderAbort(f"Playwright is not installed. {INSTALL_HINT}") from e
    return sync_playwright


class PlaywrightRenderer:
    """Owns the one headless Chromium used for the whole run.

    The browser is reused across pages, with a fresh page (and so a fresh
    browser context) per URL. Use as a context manager; entering launches the
    browser, and a launch failure raises RenderAbort straight away.
    """

    def __init__(self, playwright_factory=None):
        self._factory = playwright_factory
        self._pw = None
        self._browser = None
        self._consecutive_deaths = 0

    def __enter__(self) -> PlaywrightRenderer:
        factory = self._factory or _default_playwright_factory()
        try:
            self._pw = factory().start()
        except Exception as e:
            raise RenderAbort(f"Could not start Playwright: {e}\n{INSTALL_HINT}") from e
        try:
            self._launch()
        except BaseException:
            self._stop_playwright()
            raise
        return self

    def __exit__(self, *exc_info) -> None:
        self._close_quietly(self._browser)
        self._stop_playwright()

    def _launch(self) -> None:
        try:
            if self._pw is None:
                raise RenderAbort("Playwright is not initialized")
            self._browser = self._pw.chromium.launch(headless=True)
        except Exception as e:
            raise RenderAbort(f"Could not launch Chromium: {e}\n{INSTALL_HINT}") from e

    def fetch_text(self, url: str) -> str:
        """The visible text of the rendered page, for one URL, one attempt.

        Raises on any per-URL failure (timeout, navigation error, no body), which
        the caller records as failed_per_url. Raises RenderAbort instead if the
        browser died and can't be replaced, or has died too many times in a row.
        """
        page = None
        try:
            if self._browser is None:
                raise RenderAbort("Browser is not initialized")
            page = self._browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=PLAYWRIGHT_TIMEOUT_MS)
            text = page.inner_text("body", timeout=PLAYWRIGHT_TIMEOUT_MS)
        except Exception:
            self._after_failure()
            raise
        finally:
            self._close_quietly(page)
        self._consecutive_deaths = 0
        return sanitize_for_csv(text)

    def _after_failure(self) -> None:
        """Replace the browser if the failure killed it, for the next URL.

        The URL that was in flight is not retried. If the browser keeps dying,
        something systemic is wrong (out of memory, a broken install), so give
        up rather than mark every remaining row failed.
        """
        if self._browser is None:
            raise RenderAbort("Browser is not initialized")
        if self._browser.is_connected():
            self._consecutive_deaths = 0
            return
        self._consecutive_deaths += 1
        if self._consecutive_deaths >= PLAYWRIGHT_MAX_CONSECUTIVE_CRASHES:
            raise RenderAbort(
                f"Chromium died {self._consecutive_deaths} times in a row; "
                "aborting instead of marking every remaining row failed."
            )
        logger.warning(
            "Chromium died (%d in a row); relaunching", self._consecutive_deaths,
        )
        self._close_quietly(self._browser)
        self._launch()

    @staticmethod
    def _close_quietly(closable) -> None:
        # Closing can itself raise when the browser is already gone, and there
        # is nothing left to clean up in that case.
        if closable is None:
            return
        try:
            closable.close()
        except Exception as e:
            logger.debug("close() raised, ignoring: %s", e)

    def _stop_playwright(self) -> None:
        try:
            if self._pw is None:
                raise RenderAbort("Playwright is not initialized")
            self._pw.stop()
        except Exception as e:
            logger.debug("playwright stop() raised, ignoring: %s", e)


def render_row(row: dict, renderer, extract=extract_with_retries) -> dict:
    """The Stage 3 version of one Stage 2 row.

    `renderer` is anything with fetch_text(url) -> str (a PlaywrightRenderer).
    Extract and Playwright failures are recorded on the row, never as
    sentinels. Only RenderAbort escapes, and the caller must let it.
    """
    out = dict(row)
    if not is_keep(row) or is_sentinel(row):
        out.update(extract_status="", render_status="", content_source="")
        return out

    url = row["result_url"]
    content = row["result_raw_content"] or ""
    if is_blank(content):
        content = ""
    source = ContentSource.SEARCH if content else ""
    extract_status = ""

    if not content:
        extract_status, text = extract(url)
        logger.debug("%s: extract %s, %d chars", url, extract_status, len(text))
        if not is_blank(text):
            content, source = text, ContentSource.EXTRACT

    render_status = RenderStatus.NOT_NEEDED
    if needs_playwright(content, url):
        try:
            text = renderer.fetch_text(url)
        except RenderAbort:
            raise
        except Exception as e:
            logger.debug("%s: playwright raised: %s", url, e)
            render_status = RenderStatus.FAILED_PER_URL
        else:
            if is_blank(text):
                render_status = RenderStatus.FAILED_PER_URL
            else:
                render_status = RenderStatus.SUCCEEDED
                # Only replace with more text: Playwright text carries no link
                # hrefs, so it must earn the swap. Lengths compare markdown
                # against plain text, which favours the markdown a little.
                if not content or len(text) > len(content):
                    content, source = text, ContentSource.PLAYWRIGHT
        logger.debug("%s: playwright %s, now %d chars", url, render_status, len(content))

    out.update(
        extract_status=extract_status,
        raw_content_length=len(content),
        result_raw_content=content,
        render_status=render_status,
        content_source=source if content else "",
    )
    return out


def output_fieldnames(input_fieldnames: Sequence[str]) -> list[str]:
    """Stage 3's output columns; the order is defined in schema.py."""
    return rendered_fieldnames(input_fieldnames)


def check_input_columns(fieldnames: Sequence[str], path: str) -> None:
    require_columns(path, fieldnames, REQUIRED_INPUT_COLUMNS)
    already = [c for c in NEW_FIELDNAMES if c in fieldnames]
    if already:
        raise ValueError(
            f"{path} already has Stage 3 columns {already}, so it is not a "
            "current Stage 2 output."
        )


def main(
    input_csv: str = DEFAULT_FILTERED_CSV, output_csv: str = RENDERED_RESULTS_CSV
) -> None:
    with open(input_csv, newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames or []

        # Validate decisions before opening the output or starting the browser.
        check_input_columns(fieldnames, input_csv)
        has_keeps = False
        for row in reader:
            has_keeps = has_keeps or is_keep(row)
        f_in.seek(0)
        reader = csv.DictReader(f_in)

        # Validate the browser before extract calls when any row will be used.
        renderer_context = PlaywrightRenderer() if has_keeps else nullcontext(None)
        with renderer_context as renderer:
            with open(output_csv, "w", newline="", encoding="utf-8") as f_out:
                writer = csv.DictWriter(
                    f_out,
                    fieldnames=output_fieldnames(fieldnames),
                    extrasaction="ignore",
                )
                writer.writeheader()

                for row in reader:
                    writer.writerow(render_row(row, renderer))
                    # Flushed per row so a run that aborts or crashes leaves a
                    # salvageable partial file. There is no resume.
                    f_out.flush()


if __name__ == "__main__":
    args = build_parser(
        "Stage 3: repair blank or short page text on kept rows.",
        DEFAULT_FILTERED_CSV,
        RENDERED_RESULTS_CSV,
    ).parse_args()
    main(args.input_csv, args.output_csv)