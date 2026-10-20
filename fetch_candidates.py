"""Stage 1: search for candidate TTRPG club pages and record the raw results.

For each college we run every query template through Tavily, asking for each
hit's page text, and de-duplicate hits by URL. Every search hit gets a row
whether or not its text was found; columns that don't apply are left blank.
Input columns (except SEARCH_DROPPED_FIELDNAMES) are carried onto each output row,
so later stages never need to join back to it.

Page text comes from the search call only. Hits whose text came back blank or
suspiciously short are repaired by render_candidates.py (Stage 3), which
re-fetches kept rows with Tavily extract() and Playwright after Stage 2 filters.

This makes no judgement about whether a result is a club page and computes no
keyword signals. filter_candidates.py reads this output and records its
keyword decision offline as Stage 2.

Setup:
    pip install tavily-python python-dotenv
    Create .env with: TAVILY_API_KEY=tvly-... and TTRPG_DEBUG=0 or 1

Set TTRPG_DEBUG=1 in .env for per-college funnel logging and a raw_content
preview for the first few colleges.
"""

from __future__ import annotations
from config import (
    DEFAULT_INPUT_CSV, EXCLUDED_DOMAINS_PATH,
    MAX_RESULTS_PER_QUERY, MAX_UNCONFIRMED_SEARCH_CREDITS,
    QUERY_TEMPLATES_PATH, RAW_CONTENT_FORMAT,
    RAW_CONTENT_PREVIEW_COUNT, SEARCH_COUNTRY, SEARCH_DEPTH,
    SEARCH_RESULTS_CSV, SLEEP_BETWEEN_COLLEGES_S,
    load_query_templates, load_word_list,
)
from schema import SEARCH_NEW_FIELDNAMES, SEARCH_DROPPED_FIELDNAMES, require_columns
from search_row_format_util import ERROR_URL, NO_RESULTS_PREFIX, sanitize_for_csv
from stage_cli import build_parser
from tavily_client_util import tavily

import csv
import logging
import os
import time
from dataclasses import dataclass, field


DEBUG = os.environ.get("TTRPG_DEBUG") == "1"

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("fetch_candidates")
logger.setLevel(logging.DEBUG if DEBUG else logging.WARNING)


class RawStatus:
    """What the search call returned as a hit's page text."""

    SUCCEEDED = "succeeded"
    EMPTY = "empty"      # "" or whitespace only
    MISSING = "missing"  # null or absent


# Credits one search() call costs at each search_depth (Tavily's pricing).
CREDITS_PER_SEARCH = {"advanced": 2}


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
            "raw_content_length": len(self.raw_content),
            # The page text is large, but Stage 3 may repair it and Stage 4
            # scans it for contact signals, so it must remain in this handoff.
            "result_raw_content": self.raw_content,
        }


def search_college(
    name: str, query_templates: list[str], excluded_domains: list[str],
) -> tuple[list[SearchResult], list[SearchError]]:
    """Run every query template for one college, de-duplicated by URL.

    Page text arrives with each hit; blank or suspiciously short text is left
    for Stage 3 to repair. There is no quality filter here — Stage 2 makes
    that call.
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
        "%s: %d raw -> %d deduped -> %d with blank page text",
        name, n_raw, len(results), len(blank),
    )
    for result in blank:
        logger.debug(
            "%s: search returned %s page text for %s",
            name, result.raw_content_status, result.url,
        )

    return list(results.values()), errors


def log_raw_content(name: str, results: list[SearchResult]) -> None:
    for result in results:
        if result.raw_content:
            logger.debug(
                "%s: raw_content preview for %s (%d chars): %r",
                name, result.url, len(result.raw_content),
                result.raw_content,
            )


def estimate_search_credits(n_colleges: int, n_templates: int) -> int:
    return n_colleges * n_templates * CREDITS_PER_SEARCH.get(SEARCH_DEPTH, 1)


def main(
    input_csv: str = DEFAULT_INPUT_CSV,
    output_csv: str = SEARCH_RESULTS_CSV,
    limit: int | None = None,
    assume_yes: bool = False,
) -> None:
    query_templates = load_query_templates(QUERY_TEMPLATES_PATH)
    excluded_domains = load_word_list(EXCLUDED_DOMAINS_PATH)

    with open(input_csv, newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        require_columns(input_csv, reader.fieldnames, ["college_name"])
        carried = [c for c in reader.fieldnames or [] if c not in SEARCH_DROPPED_FIELDNAMES]
        rows = list(reader)
    if limit is not None:
        rows = rows[:limit]

    # Checked before the output is opened, so a refusal doesn't truncate an
    # earlier run's file or spend any credits.
    credits = estimate_search_credits(len(rows), len(query_templates))
    if credits > MAX_UNCONFIRMED_SEARCH_CREDITS and not assume_yes:
        raise SystemExit(
            f"Estimated {credits} Tavily credits ({len(rows)} colleges x "
            f"{len(query_templates)} queries, search_depth={SEARCH_DEPTH}) "
            f"exceeds {MAX_UNCONFIRMED_SEARCH_CREDITS}. Pass --yes to run, or "
            "--limit N to run a sample."
        )

    with open(output_csv, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=carried + SEARCH_NEW_FIELDNAMES)
        writer.writeheader()

        for index, row in enumerate(rows):
            name = row["college_name"]
            institution = {c: row[c] for c in carried}
            results, errors = search_college(name, query_templates, excluded_domains)

            if index < RAW_CONTENT_PREVIEW_COUNT:
                log_raw_content(name, results)

            if not results and not errors:
                tried = "; ".join(t.format(name=name) for t in query_templates)
                writer.writerow({
                    **institution,
                    "search_query": f"{NO_RESULTS_PREFIX} {tried}",
                })

            for error in errors:
                writer.writerow({
                    **institution,
                    "search_query": error.query,
                    "result_url": ERROR_URL, "result_title": error.message,
                })

            for result in results:
                writer.writerow({**institution, **result.to_csv_row()})

            time.sleep(SLEEP_BETWEEN_COLLEGES_S)


if __name__ == "__main__":
    parser = build_parser(
        "Stage 1: search Tavily for candidate club pages.",
        DEFAULT_INPUT_CSV,
        SEARCH_RESULTS_CSV,
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="search only the first N colleges of the input",
    )
    parser.add_argument(
        "--yes", dest="assume_yes", action="store_true",
        help="run even if the estimated Tavily cost exceeds the safety cap",
    )
    args = parser.parse_args()
    main(args.input_csv, args.output_csv, args.limit, args.assume_yes)