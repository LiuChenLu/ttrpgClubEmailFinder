"""Search for candidate TTRPG club pages per college and record raw signals.

For each college we run every query template through Tavily, de-duplicate hits
by URL, and for the promising ones fetch the page text and scan it for TTRPG
keywords and contact info (emails, Discord invites).

This does NOT decide whether a result actually is a club page. That
classification step is a separate follow-up; this script produces the raw
evidence a human or an LLM can use to make that call later.

Setup:
    pip install tavily-python python-dotenv
    Create .env with: TAVILY_API_KEY=tvly-... and TTRPG_DEBUG=0 or 1

Set TTRPG_DEBUG=1 in .env for per-college funnel logging, extract()
diagnostics, a raw_content preview for the first few colleges, and an extra
`keywords_matched` column in the output CSV.
"""

from __future__ import annotations

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

from config import (
    DEFAULT_INPUT_CSV, DEFAULT_RESULTS_CSV, EXCLUDED_DOMAINS,
    MAX_RESULTS_PER_QUERY, QUERY_TEMPLATES, RAW_CONTENT_PREVIEW_COUNT,
    SEARCH_DEPTH, SLEEP_BETWEEN_COLLEGES_S, SNIPPET_CHARS,
    TAVILY_RELEVANCE_THRESHOLD, TTRPG_KEYWORDS,
)

DEBUG = bool(os.environ.get("TTRPG_DEBUG"))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("find_ttrpg_clubs")
logger.setLevel(logging.DEBUG if DEBUG else logging.WARNING)

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}")
DISCORD_RE = re.compile(r"(?:discord\.gg|discord\.com/invite)/[A-Za-z0-9-]+")

# Control chars (NULs turn up in scraped text) make strict CSV parsers truncate
# or refuse the file, and a bare \r inside a quoted field is mis-parsed by some
# grid tools. Neither carries meaning, so drop/normalise them. Do NOT add any
# other escaping here: csv already does RFC 4180 quoting and stacking our own
# on top would double-escape the output.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class Status:
    """Why a row has no raw_content. Exactly one value applies per result row."""

    LOW_SCORE = "not_attempted_low_score"
    NO_KEYWORD = "not_attempted_no_keyword_snippet"
    EXCEPTION = "attempt_failed_exception"
    PER_URL_FAILED = "attempt_failed_per_url"
    NO_RESPONSE_ENTRY = "attempt_no_response_entry"
    SUCCEEDED_EMPTY = "attempt_succeeded_empty"
    SUCCEEDED = "attempt_succeeded"


FIELDNAMES = [
    "unitid", "college_name", "matched_query",
    "result_url", "result_title", "result_snippet",
    "result_score", "passed_score_gate", "passed_keyword_gate",
    "raw_content_status", "extract_error",
    "result_raw_content", "raw_content_length",
    "emails_found", "discord_links_found", "emails_found_in_snippet",
    "has_any_contact_signal",
] + (["keywords_matched"] if DEBUG else [])


@functools.cache
def tavily() -> TavilyClient:
    """Built lazily so importing this module doesn't require the API key."""
    return TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


def sanitize_for_csv(text: str) -> str:
    if not text:
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL_CHAR_RE.sub("", text)


def find_ttrpg_keywords(text: str) -> list[str]:
    lowered = text.lower()
    return [kw for kw in TTRPG_KEYWORDS if kw in lowered]


def find_contact_signals(text: str) -> tuple[list[str], list[str]]:
    # TODO: try to find a contact name.
    # TODO: distinguish multiple emails (club president vs. club group address).
    return EMAIL_RE.findall(text), DISCORD_RE.findall(text)


# TODO: special-case club hosting vendors, each identifiable from the page
# source: CampusGroups ("Powered by CampusGroups"), Modern Campus Involve,
# Anthology Engage, Lounge, Corq.


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
    keywords: list[str] = field(default_factory=list)
    snippet_emails: list[str] = field(default_factory=list)
    raw_content: str = ""
    extract_error: str = ""
    status: str = ""

    def __post_init__(self) -> None:
        # Gate failures are terminal; anything else is resolved by extract().
        if not self.passed_score_gate:
            self.status = Status.LOW_SCORE
        elif not self.passed_keyword_gate:
            self.status = Status.NO_KEYWORD

    @classmethod
    def from_tavily(cls, query: str, result: dict) -> SearchResult | None:
        url = result.get("url", "")
        if not url:
            return None
        title = sanitize_for_csv(result.get("title", ""))
        snippet = sanitize_for_csv(result.get("content", "") or "")
        emails, _ = find_contact_signals(snippet)
        return cls(
            query=query,
            url=url,
            title=title,
            snippet=snippet,
            score=result.get("score", 0.0),
            keywords=find_ttrpg_keywords(f"{title} {snippet}"),
            snippet_emails=emails,
        )

    @property
    def passed_score_gate(self) -> bool:
        return self.score >= TAVILY_RELEVANCE_THRESHOLD

    @property
    def passed_keyword_gate(self) -> bool:
        return bool(self.keywords)

    @property
    def qualifies_for_extract(self) -> bool:
        return self.passed_score_gate and self.passed_keyword_gate

    def to_csv_row(self, unitid: str, college_name: str) -> dict:
        emails, discord_links = find_contact_signals(self.raw_content)
        row = {
            "unitid": unitid,
            "college_name": college_name,
            "matched_query": self.query,
            "result_url": self.url,
            "result_title": self.title,
            "result_snippet": self.snippet[:SNIPPET_CHARS],
            "result_score": self.score,
            "passed_score_gate": self.passed_score_gate,
            "passed_keyword_gate": self.passed_keyword_gate,
            "raw_content_status": self.status,
            "extract_error": self.extract_error,
            "result_raw_content": self.raw_content,
            "raw_content_length": len(self.raw_content),
            "emails_found": "; ".join(emails),
            "discord_links_found": "; ".join(discord_links),
            "emails_found_in_snippet": "; ".join(self.snippet_emails),
            "has_any_contact_signal": bool(
                emails or discord_links or self.snippet_emails
            ),
        }
        if DEBUG:
            row["keywords_matched"] = "; ".join(self.keywords)
        return row


def search_college(name: str) -> tuple[list[SearchResult], list[SearchError]]:
    """Run every query template for one college, de-duplicated by URL.

    When a URL comes back from more than one template, the higher-scoring hit
    wins — see the loop below.

    Page text is fetched only for results clearing both gates, via a separate
    extract() call rather than include_raw_content on every hit, so we don't
    pay extraction cost for results unlikely to be a club page.
    """
    results: dict[str, SearchResult] = {}
    errors: list[SearchError] = []
    n_raw = 0

    for template in QUERY_TEMPLATES:
        query = template.format(name=name)
        try:
            response = tavily().search(
                query=query,
                max_results=MAX_RESULTS_PER_QUERY,
                search_depth=SEARCH_DEPTH,
                exclude_domains=EXCLUDED_DOMAINS,
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
            # rather than whichever template happened to run first, so the
            # gates and result_score reflect the best evidence we have for
            # that page.
            existing = results.get(result.url)
            if existing is None or result.score > existing.score:
                results[result.url] = result

    qualifying = [r.url for r in results.values() if r.qualifies_for_extract]
    logger.debug(
        "%s: %d raw -> %d deduped -> %d passed score, %d passed keyword, %d both",
        name, n_raw, len(results),
        sum(r.passed_score_gate for r in results.values()),
        sum(r.passed_keyword_gate for r in results.values()),
        len(qualifying),
    )
    if qualifying:
        extract_raw_content(name, results, qualifying)

    return list(results.values()), errors


def extract_raw_content(
    name: str, results: dict[str, SearchResult], urls: list[str]
) -> None:
    """Fetch page text for `urls`, updating those results in place.

    A failed extraction doesn't invalidate the search hit, so affected rows keep
    an empty raw_content but record why via status/extract_error.
    """
    try:
        response = tavily().extract(urls=urls, format="text")
    except Exception as e:
        logger.debug("%s: extract() raised for all %d URLs: %s", name, len(urls), e)
        for url in urls:
            results[url].status = Status.EXCEPTION
            results[url].extract_error = str(e)
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
            results[url].extract_error = entry.get("error", "")
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
    with open(input_csv, newline="", encoding="utf-8") as f_in, \
         open(output_csv, "w", newline="", encoding="utf-8") as f_out:

        writer = csv.DictWriter(f_out, fieldnames=FIELDNAMES)
        writer.writeheader()

        for index, row in enumerate(csv.DictReader(f_in)):
            unitid, name = row["UNITID"], row["NAME"]
            results, errors = search_college(name)

            if index < RAW_CONTENT_PREVIEW_COUNT:
                log_raw_content_preview(name, results)

            if not results and not errors:
                tried = "; ".join(t.format(name=name) for t in QUERY_TEMPLATES)
                writer.writerow({
                    "unitid": unitid, "college_name": name,
                    "matched_query": f"NO_RESULTS: {tried}",
                })

            for error in errors:
                writer.writerow({
                    "unitid": unitid, "college_name": name,
                    "matched_query": error.query,
                    "result_url": "ERROR", "result_title": error.message,
                })

            for result in results:
                writer.writerow(result.to_csv_row(unitid, name))

            time.sleep(SLEEP_BETWEEN_COLLEGES_S)


if __name__ == "__main__":
    main()