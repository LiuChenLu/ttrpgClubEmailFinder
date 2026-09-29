"""Stage 1: search for candidate TTRPG club pages and record raw signals.

For each college we run every query template through Tavily, de-duplicate hits
by URL (keeping the higher score when a URL recurs across templates), and
fetch the page text for the top-scoring candidates (see
MAX_CANDIDATES_PER_COLLEGE). Every search hit gets a row whether or not it was
extracted; columns that don't apply are left blank. Every input column is
carried onto each output row, so later stages never need to join back to it.

Two keyword tiers are recorded, neither of them a gate or a verdict:
  - snippet (OR): at least one list matched title+snippet. Recorded only.
  - text (AND): what each list matched in the extracted page. Recorded only;
    extract_contact_info.py applies it as a gate.

This does NOT decide whether a result actually is a club page, and it makes no
contact-info judgements. Stage 2 reads this CSV and does that offline.

Setup:
    pip install tavily-python python-dotenv
    Create .env with: TAVILY_API_KEY=tvly-... and TTRPG_DEBUG=0 or 1

Set TTRPG_DEBUG=1 in .env for per-college funnel logging, extract()
diagnostics, and a raw_content preview for the first few colleges.
"""

from __future__ import annotations
from config import (
    CLUB_KEYWORDS_PATH, DEFAULT_INPUT_CSV, DEFAULT_RESULTS_CSV,
    EXCLUDED_DOMAINS_PATH, MAX_RESULTS_PER_QUERY, QUERY_TEMPLATES_PATH,
    RAW_CONTENT_PREVIEW_COUNT, SEARCH_DEPTH, SLEEP_BETWEEN_COLLEGES_S,
    SNIPPET_CHARS, TTRPG_KEYWORDS_PATH,
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


DEBUG = bool(os.environ.get("TTRPG_DEBUG"))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("classify_club_pages")
logger.setLevel(logging.DEBUG if DEBUG else logging.WARNING)

# No score or keyword floor gates extraction anymore — every college with at
# least one search hit gets up to this many of its highest-scoring results
# fetched in full, regardless of how weak the best of them looks.
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
    "club_keywords_found_in_snippet", "ttrpg_keywords_found_in_snippet",
    "club_keywords_found_in_text", "ttrpg_keywords_found_in_text",
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


def find_keywords(text: str, keywords: list[str]) -> list[str]:
    lowered = text.lower()
    return [kw for kw in keywords if kw in lowered]


# TODO: special-case club hosting vendors, each identifiable from the page
# source: CampusGroups ("Powered by CampusGroups"), Modern Campus Involve,
# Anthology Engage, Lounge, Corq.

# TODO: detect when a URL is a directory of a university's clubs rather than
# one specific club's page. These often rank well and mention plenty of
# keywords (an A-Z list mentions "club" and often "tabletop"), but yield no
# single club's contact info, so they need separating before anything
# downstream treats a row as one club.


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
    club_keywords_snippet: list[str] = field(default_factory=list)
    ttrpg_keywords_snippet: list[str] = field(default_factory=list)
    club_keywords_text: list[str] = field(default_factory=list)
    ttrpg_keywords_text: list[str] = field(default_factory=list)
    raw_content: str = ""
    raw_content_error: str = ""
    status: str = ""

    @classmethod
    def from_tavily(
        cls, query: str, result: dict, ttrpg_kw: list[str], club_kw: list[str]
    ) -> SearchResult | None:
        url = result.get("url", "")
        if not url:
            return None
        title = sanitize_for_csv(result.get("title", ""))
        snippet = sanitize_for_csv(result.get("content", "") or "")
        haystack = f"{title} {snippet}"
        return cls(
            query=query,
            url=url,
            title=title,
            snippet=snippet,
            score=result.get("score", 0.0),
            club_keywords_snippet=find_keywords(haystack, club_kw),
            ttrpg_keywords_snippet=find_keywords(haystack, ttrpg_kw),
        )

    def scan_text(self, ttrpg_kw: list[str], club_kw: list[str]) -> None:
        """Record what each list matched in the extracted page.

        Left empty unless extraction actually returned text, so a blank column
        means "not measured", never "measured and found nothing".
        """
        self.club_keywords_text = find_keywords(self.raw_content, club_kw)
        self.ttrpg_keywords_text = find_keywords(self.raw_content, ttrpg_kw)

    def to_csv_row(self) -> dict:
        return {
            "search_query": self.query,
            "result_url": self.url,
            "result_title": self.title,
            "result_snippet": self.snippet[:SNIPPET_CHARS],
            "result_score": self.score,
            "club_keywords_found_in_snippet": "; ".join(self.club_keywords_snippet),
            "ttrpg_keywords_found_in_snippet": "; ".join(self.ttrpg_keywords_snippet),
            "club_keywords_found_in_text": "; ".join(self.club_keywords_text),
            "ttrpg_keywords_found_in_text": "; ".join(self.ttrpg_keywords_text),
            "raw_content_status": self.status,
            "raw_content_error": self.raw_content_error,
            # TODO: the full run should not carry whole pages in this column —
            # it is the bulk of the file size and nothing downstream of stage 2
            # needs it. Written in full only so the current test runs can be
            # eyeballed against the keyword and contact columns.
            "result_raw_content": self.raw_content,
            "raw_content_length": len(self.raw_content),
        }


def search_college(
    name: str, ttrpg_kw: list[str], club_kw: list[str],
    query_templates: list[str], excluded_domains: list[str],
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
            result = SearchResult.from_tavily(query, raw, ttrpg_kw, club_kw)
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
        for result in selected:
            if result.status == Status.SUCCEEDED:
                result.scan_text(ttrpg_kw, club_kw)

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
                result.raw_content[:SNIPPET_CHARS],
            )


def main(input_csv: str = DEFAULT_INPUT_CSV, output_csv: str = DEFAULT_RESULTS_CSV) -> None:
    ttrpg_kw = load_word_list(TTRPG_KEYWORDS_PATH)
    club_kw = load_word_list(CLUB_KEYWORDS_PATH)
    query_templates = load_query_templates(QUERY_TEMPLATES_PATH)
    excluded_domains = load_word_list(EXCLUDED_DOMAINS_PATH)

    with open(input_csv, newline="", encoding="utf-8") as f_in, \
            open(output_csv, "w", newline="", encoding="utf-8") as f_out:

        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(
            f_out, fieldnames=reader.fieldnames + NEW_FIELDNAMES
        )
        writer.writeheader()

        for index, row in enumerate(reader):
            name = row["college_name"]
            results, errors = search_college(
                name, ttrpg_kw, club_kw, query_templates, excluded_domains
            )

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