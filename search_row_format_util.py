"""The conventions of the search-result rows Stage 1 writes and later stages carry on.

Covers how page text is sanitized for CSV, and how sentinel rows (a failure
logged in place of a result) are marked and detected. The markers are shared
constants so the code that writes sentinel rows (fetch_candidates.py) and the
code that detects them (render_candidates.py) can't drift apart.

Has no dependency on the tavily package or on .env, so any stage can import it
without an API key. Importing it raises csv's field-size limit.
"""

from __future__ import annotations

import csv
import re

# Page text can exceed csv's default 128 KB field limit when read back.
# 2**31 - 1 is the largest value that doesn't overflow on Windows.
csv.field_size_limit(2**31 - 1)

# Sentinel rows log a failure instead of describing a search result. Stage 1
# writes two kinds: an ERROR row (result_url is ERROR_URL, and the exception
# message is in result_title) and a NO_RESULTS row (search_query starts with
# NO_RESULTS_PREFIX, and result_url is blank).
ERROR_URL = "ERROR"
NO_RESULTS_PREFIX = "NO_RESULTS:"

# Control chars (NULs turn up in scraped text) make strict CSV parsers truncate
# or refuse the file, and a bare \r inside a quoted field is mis-parsed by some
# grid tools. Neither carries meaning, so drop/normalise them. Do NOT add any
# other escaping here: csv already does RFC 4180 quoting and stacking our own
# on top would double-escape the output.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_for_csv(text: str) -> str:
    if not text:
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL_CHAR_RE.sub("", text)


def is_sentinel(row: dict) -> bool:
    """True for the ERROR / NO_RESULTS rows that log a failure, not a page.

    A blank result_url counts too: Stage 1 never writes a real row without one,
    so a blank URL can only be a sentinel (or a corrupt row to discard anyway).
    """
    return (
        not row.get("result_url")
        or row["result_url"] == ERROR_URL
        or (row.get("search_query") or "").startswith(NO_RESULTS_PREFIX)
    )