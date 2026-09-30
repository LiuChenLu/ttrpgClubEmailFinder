"""Stage 1: search for candidate TTRPG club pages and record the raw results.

For each college we run every query template through Tavily, de-duplicate hits
by URL (keeping the higher score when a URL recurs across templates), and
fetch the page text for the top-scoring candidates (see
MAX_CANDIDATES_PER_COLLEGE). Every search hit gets a row whether or not it was
extracted; columns that don't apply are left blank. Every input column is
carried onto each output row, so later stages never need to join back to it.

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
    DEFAULT_CANDIDATES_CSV, DEFAULT_INPUT_CSV, EXCLUDED_DOMAINS_PATH,
    MAX_RESULTS_PER_QUERY, QUERY_TEMPLATES_PATH, RAW_CONTENT_PREVIEW_COUNT,
    SEARCH_DEPTH, SLEEP_BETWEEN_COLLEGES_S,
    load_query_templates, load_word_list,
)

import csv
import functools
import logging
import os
import re
import time
from dataclasses import dataclass

from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()


DEBUG = bool(os.environ.get("TTRPG_DEBUG"))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("fetch_candidates")
logger.setLevel(logging.DEBUG if DEBUG else logging.WARNING)

# No score floor gates extraction — every college with at least one search hit
# gets up to this many of its highest-scoring results fetched in full,
# regardless of how weak the best of them looks.
MAX_CANDIDATES_PER_COLLEGE = 3

# Control chars (NULs turn up in scraped text) make strict CSV parsers truncate
# or refuse the file, and a bare \r inside a quoted field is mis-parsed by some
# grid tools. Neither carries meaning, so drop/normalise them. Do NOT add any
# other escaping here: csv already does RFC 4180 quoting and stacking our own
# on top would double-escape the output.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class Status:
    """Why a row has no raw_content. Exactly one value applies per result row."""

    NOT_TOP_CANDIDATE = "not_attempted_not_top_candidate"
    EXCEPTION = "attempt_failed_exception"
    PER_URL_FAILED = "attempt_failed_per_url"
    NO_RESPONSE_ENTRY = "attempt_no_response_entry"
    SUCCEEDED_EMPTY = "attempt_succeeded_empty"
    SUCCEEDED = "attempt_succeeded"


# Columns this stage adds. The input CSV's own columns are prepended in main().
NEW_FIELDNAMES = [
    "search_query",
    "result_url", "result_title", "result_snippet", "result_score",
    "raw_content_status", "raw_content_error",
    "result_raw_content", "raw_content_length",
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
    snippet: str
    score: float
    raw_content: str = ""
    raw_content_error: str = ""
    status: str = ""

    @classmethod
    def from_tavily(cls, query: str, result: dict) -> SearchResult | None:
        url = result.get("url", "")
        if not url:
            return None
        return cls(
            query=query,
            url=url,
            title=sanitize_for_csv(result.get("title", "")),
            snippet=sanitize_for_csv(result.get("content", "") or ""),
            score=result.get("score", 0.0),
        )

    def to_csv_row(self) -> dict:
        return {
            "search_query": self.query,
            "result_url": self.url,
            "result_title": self.title,
            "result_snippet": self.snippet,
            "result_score": self.score,
            "raw_content_status": self.status,
            "raw_content_error": self.raw_content_error,
            # TODO: the full run should not carry whole pages in this column —
            # it is the bulk of the file size and nothing downstream of stage 2
            # needs it. Written in full only so the current test runs can be
            # eyeballed.
            "result_raw_content": self.raw_content,
            "raw_content_length": len(self.raw_content),
        }


def search_college(
    name: str, query_templates: list[str], excluded_domains: list[str],
) -> tuple[list[SearchResult], list[SearchError]]:
    """Run every query template for one college, de-duplicated by URL.

    When a URL comes back from more than one template, the higher-scoring hit
    wins — see the loop below.

    Page text is fetched only for the MAX_CANDIDATES_PER_COLLEGE
    highest-scoring results, via a separate extract() call rather than
    include_raw_content on every hit, so we don't pay extraction cost for
    every result a college's queries turn up.
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
                exclude_domains=excluded_domains,
            )
        except Exception as e:
            errors.append(SearchError(query, str(e)))
            logger.debug("%s: query %r raised: %s", name, query, e)
            continue

        for raw in response.get("results", []):
            n_raw += 1
            result = SearchResult.from_tavily(query, raw)
            if not result:
                continue
            # A URL can surface from more than one query template with a
            # different score/snippet each time. Keep the higher-scoring hit
            # rather than whichever template happened to run first, so
            # result_score reflects the best evidence we have for that page.
            existing = results.get(result.url)
            if existing is None or result.score > existing.score:
                results[result.url] = result

    selected = sorted(
        results.values(), key=lambda r: r.score, reverse=True
    )[:MAX_CANDIDATES_PER_COLLEGE]
    selected_urls = {r.url for r in selected}
    for result in results.values():
        if result.url not in selected_urls:
            result.status = Status.NOT_TOP_CANDIDATE

    logger.debug(
        "%s: %d raw -> %d deduped -> %d selected as candidates",
        name, n_raw, len(results), len(selected),
    )
    if selected:
        extract_raw_content(name, results, [r.url for r in selected])

    return list(results.values()), errors


def extract_raw_content(
    name: str, results: dict[str, SearchResult], urls: list[str]
) -> None:
    """Fetch page text for `urls`, updating those results in place.

    A failed extraction doesn't invalidate the search hit, so affected rows keep
    an empty raw_content but record why via status/raw_content_error.
    """
    try:
        response = tavily().extract(urls=urls, format="text")
    except Exception as e:
        logger.debug("%s: extract() raised for all %d URLs: %s", name, len(urls), e)
        for url in urls:
            results[url].status = Status.EXCEPTION
            results[url].raw_content_error = str(e)
        return

    answered = set()
    for extracted in response.get("results", []):
        url = extracted.get("url", "")
        if url in results:
            content = sanitize_for_csv(extracted.get("raw_content", "") or "")
            results[url].raw_content = content
            results[url].status = Status.SUCCEEDED if content else Status.SUCCEEDED_EMPTY
            answered.add(url)

    # Tavily reports per-URL failures here rather than raising; without reading
    # this list they're indistinguishable from "never attempted".
    failed = response.get("failed_results", [])
    for entry in failed:
        url = entry.get("url", "")
        if url in results:
            results[url].status = Status.PER_URL_FAILED
            results[url].raw_content_error = entry.get("error", "")
            answered.add(url)

    # Shouldn't happen, but don't silently drop a URL Tavily never mentions.
    for url in urls:
        if url not in answered:
            results[url].status = Status.NO_RESPONSE_ENTRY

    logger.debug(
        "%s: extract() requested %d, %d returned, %d failed%s",
        name, len(urls), len(response.get("results", [])), len(failed),
        f": {failed}" if failed else "",
    )


def log_raw_content_preview(name: str, results: list[SearchResult]) -> None:
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
        writer = csv.DictWriter(
            f_out, fieldnames=list(reader.fieldnames) + NEW_FIELDNAMES if reader.fieldnames is not None else NEW_FIELDNAMES
        )
        writer.writeheader()

        for index, row in enumerate(reader):
            name = row["college_name"]
            results, errors = search_college(name, query_templates, excluded_domains)

            if index < RAW_CONTENT_PREVIEW_COUNT:
                log_raw_content_preview(name, results)

            if not results and not errors:
                tried = "; ".join(t.format(name=name) for t in query_templates)
                writer.writerow({
                    **row,
                    "search_query": f"NO_RESULTS: {tried}",
                })

            for error in errors:
                writer.writerow({
                    **row,
                    "search_query": error.query,
                    "result_url": "ERROR", "result_title": error.message,
                })

            for result in results:
                writer.writerow({**row, **result.to_csv_row()})

            time.sleep(SLEEP_BETWEEN_COLLEGES_S)


if __name__ == "__main__":
    main()