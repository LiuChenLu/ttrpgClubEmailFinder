"""Stage 1: search for candidate TTRPG club pages and record the raw results.

For each college we run every query template through Tavily, asking for each
hit's page text, and de-duplicate hits by URL. Hits that came back with no page
text get a fallback extract(). Every search hit gets a row whether or not its
text was found; columns that don't apply are left blank. Input columns (except
DROPPED_INPUT_COLUMNS) are carried onto each output row, so later stages never
need to join back to it.

This makes no judgement about whether a result is a club page and computes no
keyword signals. filter_candidates.py reads this CSV and does that offline.

Setup:
    pip install tavily-python python-dotenv
    Create .env with: TAVILY_API_KEY=tvly-... and TTRPG_DEBUG=0 or 1

Set TTRPG_DEBUG=1 in .env for per-college funnel logging, extract()
diagnostics, and a raw_content preview for the first few colleges.
"""

from __future__ import annotations
from config import (
    DEFAULT_CANDIDATES_CSV, DEFAULT_INPUT_CSV, DROPPED_INPUT_COLUMNS,
    EXCLUDED_DOMAINS_PATH, EXTRACT_DEPTH, EXTRACT_MAX_ATTEMPTS,
    EXTRACT_RETRY_SLEEP_S, MAX_RESULTS_PER_QUERY, QUERY_TEMPLATES_PATH,
    RAW_CONTENT_FORMAT, RAW_CONTENT_PREVIEW_COUNT, SEARCH_COUNTRY,
    SEARCH_DEPTH, SLEEP_BETWEEN_COLLEGES_S,
    load_query_templates, load_word_list,
)

import csv
import functools
import logging
import os
import re
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()


DEBUG = os.environ.get("TTRPG_DEBUG") == "1"

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("fetch_candidates")
logger.setLevel(logging.DEBUG if DEBUG else logging.WARNING)

# Page text can exceed csv's default 128 KB field limit when read back.
# 2**31 - 1 is the largest value that doesn't overflow on Windows.
csv.field_size_limit(2**31 - 1)

# Control chars (NULs turn up in scraped text) make strict CSV parsers truncate
# or refuse the file, and a bare \r inside a quoted field is mis-parsed by some
# grid tools. Neither carries meaning, so drop/normalise them. Do NOT add any
# other escaping here: csv already does RFC 4180 quoting and stacking our own
# on top would double-escape the output.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class RawStatus:
    """What the search call returned as a hit's page text."""

    SUCCEEDED = "succeeded"
    EMPTY = "empty"      # "" or whitespace only
    MISSING = "missing"  # null or absent


class ExtractStatus:
    """Outcome of the fallback extract(); the last attempt's result is kept."""

    NOT_NEEDED = "not_needed"
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

# Columns this stage adds. The input CSV's own columns are prepended in main().
NEW_FIELDNAMES = [
    "search_query", "result_title", "result_url", "result_score",
    "result_snippet", "raw_content_status", "extract_status",
    "raw_content_length", "result_raw_content",
]


@functools.cache
def tavily() -> TavilyClient:
    """Built lazily so importing this module doesn't require the API key."""
    return TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


def sanitize_for_csv(text: str) -> str:
    if not text:
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL_CHAR_RE.sub("", text)


@dataclass
class SearchError:
    """A query template that failed outright for one college."""

    query: str
    message: str


@dataclass
class SearchResult:
    """One de-duplicated search hit plus whatever we learned about it."""

    query: str
    url: str
    title: str
    score: float
    snippets: list[str] = field(default_factory=list)
    raw_content: str = ""
    raw_content_status: str = RawStatus.MISSING
    extract_status: str = ExtractStatus.NOT_NEEDED

    @classmethod
    def from_tavily(cls, query: str, result: dict) -> SearchResult | None:
        url = result.get("url", "")
        if not url:
            return None
        snippet = sanitize_for_csv(result.get("content", "") or "")
        raw = result.get("raw_content")
        text = sanitize_for_csv(raw or "")
        if raw is None:
            status = RawStatus.MISSING
        elif not text.strip():
            status = RawStatus.EMPTY
        else:
            status = RawStatus.SUCCEEDED
        return cls(
            query=query,
            url=url,
            title=sanitize_for_csv(result.get("title", "")),
            score=result.get("score", 0.0),
            snippets=[snippet] if snippet else [],
            raw_content=text if status == RawStatus.SUCCEEDED else "",
            raw_content_status=status,
        )

    def merge(self, other: SearchResult) -> SearchResult:
        """Combine two hits for the same URL.

        Query, title and score come from the higher-scoring hit, so they
        describe the best evidence for the page. Snippets differ between
        queries and filter_candidates.py looks for keywords in any of them, so
        all are kept.
        """
        best = other if other.score > self.score else self
        has_text = other if other.raw_content and not self.raw_content else self
        return SearchResult(
            query=best.query,
            url=self.url,
            title=best.title,
            score=best.score,
            snippets=self.snippets + [s for s in other.snippets if s not in self.snippets],
            raw_content=has_text.raw_content,
            raw_content_status=has_text.raw_content_status,
        )

    def to_csv_row(self) -> dict:
        return {
            "search_query": self.query,
            "result_title": self.title,
            "result_url": self.url,
            "result_score": self.score,
            "result_snippet": "\n\n".join(self.snippets),
            "raw_content_status": self.raw_content_status,
            "extract_status": self.extract_status,
            "raw_content_length": len(self.raw_content),
            # TODO: the full run should not carry whole pages in this column —
            # it is the bulk of the file size and nothing downstream of stage 2
            # needs it. Written in full only so the current test runs can be
            # eyeballed.
            "result_raw_content": self.raw_content,
        }


def search_college(
    name: str, query_templates: list[str], excluded_domains: list[str],
) -> tuple[list[SearchResult], list[SearchError]]:
    """Run every query template for one college, de-duplicated by URL.

    Page text arrives with each hit; any hit without it gets a fallback
    extract(). There is no quality filter here — Stage 2 makes that call.
    """
    results: dict[str, SearchResult] = {}
    errors: list[SearchError] = []
    n_raw = 0

    for template in query_templates:
        query = template.format(name=name)
        try:
            response = tavily().search(
                query=query,
                max_results=MAX_RESULTS_PER_QUERY,
                search_depth=SEARCH_DEPTH,
                country=SEARCH_COUNTRY,
                include_raw_content=RAW_CONTENT_FORMAT,
                exclude_domains=excluded_domains,
            )
        except Exception as e:
            errors.append(SearchError(query, str(e)))
            logger.debug("%s: query %r raised: %s", name, query, e)
            continue

        for raw in response.get("results", []):
            n_raw += 1
            hit = SearchResult.from_tavily(query, raw)
            if hit:
                existing = results.get(hit.url)
                results[hit.url] = existing.merge(hit) if existing else hit

    blank = [r for r in results.values() if not r.raw_content]
    logger.debug(
        "%s: %d raw -> %d deduped -> %d need extract",
        name, n_raw, len(results), len(blank),
    )
    for result in blank:
        logger.debug(
            "%s: search returned %s page text for %s",
            name, result.raw_content_status, result.url,
        )
        extract_raw_content(result)

    return list(results.values()), errors


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


def extract_raw_content(result: SearchResult) -> None:
    """Fill in a result's page text, retrying failed extracts.

    After the last attempt the row keeps empty text and records why in
    extract_status; a failed extraction doesn't invalidate the search hit.
    """
    for attempt in range(EXTRACT_MAX_ATTEMPTS):
        if attempt:
            time.sleep(EXTRACT_RETRY_SLEEP_S)
        result.extract_status, result.raw_content = extract_once(result.url)
        if result.extract_status not in RETRYABLE:
            return


def log_raw_content(name: str, results: list[SearchResult]) -> None:
    for result in results:
        if result.raw_content:
            logger.debug(
                "%s: raw_content preview for %s (%d chars): %r",
                name, result.url, len(result.raw_content),
                result.raw_content,
            )


def main(input_csv: str = DEFAULT_INPUT_CSV, output_csv: str = DEFAULT_CANDIDATES_CSV) -> None:
    query_templates = load_query_templates(QUERY_TEMPLATES_PATH)
    excluded_domains = load_word_list(EXCLUDED_DOMAINS_PATH)

    with open(input_csv, newline="", encoding="utf-8") as f_in, \
            open(output_csv, "w", newline="", encoding="utf-8") as f_out:

        reader = csv.DictReader(f_in)
        carried = [c for c in reader.fieldnames or [] if c not in DROPPED_INPUT_COLUMNS]
        writer = csv.DictWriter(f_out, fieldnames=carried + NEW_FIELDNAMES)
        writer.writeheader()

        for index, row in enumerate(reader):
            name = row["college_name"]
            institution = {c: row[c] for c in carried}
            results, errors = search_college(name, query_templates, excluded_domains)

            if index < RAW_CONTENT_PREVIEW_COUNT:
                log_raw_content(name, results)

            if not results and not errors:
                tried = "; ".join(t.format(name=name) for t in query_templates)
                writer.writerow({
                    **institution,
                    "search_query": f"NO_RESULTS: {tried}",
                })

            for error in errors:
                writer.writerow({
                    **institution,
                    "search_query": error.query,
                    "result_url": "ERROR", "result_title": error.message,
                })

            for result in results:
                writer.writerow({**institution, **result.to_csv_row()})

            time.sleep(SLEEP_BETWEEN_COLLEGES_S)


if __name__ == "__main__":
    main()