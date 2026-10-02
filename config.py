"""Tunable constants shared by the pipeline scripts.

Has no dependency on the tavily package, and reads no files at import time, so
any consumer can import the real thresholds without an API key or the data
files present.
"""

# a very small collection of iped institutions that have ttrpg clubs
HAS_TTRPG_CLUB_PATH = "./data/iped_institution_has_ttrpg_club.csv"
RANDOM_COLLEGE_SAMEPLE = "./data/institutions_sample.csv"
DEFAULT_INPUT_CSV = HAS_TTRPG_CLUB_PATH

# Stage 1 (fetch_candidates.py) writes CANDIDATES; stage 2
# (filter_candidates.py) reads it and writes FILTERED; stage 3
# (extract_contact_info.py) reads FILTERED and writes CONTACTS.
DEFAULT_CANDIDATES_CSV = "./data/candidates.csv"
DEFAULT_FILTERED_CSV = "./data/filtered_candidates.csv"
DEFAULT_CONTACTS_CSV = "./data/ttrpg_clubs_contacts.csv"

# --- institutions (stage 0) -------------------------------------------------
 
# One term per line, matched case-insensitively as substrings against the
# institution name. Drops school types that won't have a TTRPG club (beauty,
# cosmetology, etc.).
EXCLUDED_INSTITUTION_NAMES_PATH = "./config/excluded_institution_names.txt"

# --- search ------------------------------------------------------------

# One template per line, each containing a {name} placeholder substituted with
# the college name at query time. Kept as a data file, like the word lists
# below, so the queries can be edited without touching code.
QUERY_TEMPLATES_PATH = "./config/query_templates.txt"

MAX_RESULTS_PER_QUERY = 10

# basic (default) / fast / ultra-fast trade relevance for latency at 1 credit;
# advanced is the most relevant at 2 credits.
SEARCH_DEPTH = "advanced"

# Tavily only honors this when the search topic is "general" (its default).
SEARCH_COUNTRY = "united states"

# Page-text format for both the search hit's raw_content and the fallback
# extract(), so the result_raw_content column never mixes formats.
RAW_CONTENT_FORMAT = "markdown"

# Hits that come back with no page text get a per-URL extract(). Only failures
# are retried; an extract that succeeds with empty text is final. "advanced"
# costs 2x basic but renders JS-heavy pages.
EXTRACT_DEPTH = "basic"
EXTRACT_MAX_ATTEMPTS = 3
EXTRACT_RETRY_SLEEP_S = 2

# Input columns that are not copied onto candidates.csv rows.
DROPPED_INPUT_COLUMNS = ["distance"]

SLEEP_BETWEEN_COLLEGES_S = 0.2

# How many colleges (in input order) get a raw_content preview logged. Enough
# to catch a JS/consent-wall stub early in a run without hundreds of log lines.
RAW_CONTENT_PREVIEW_COUNT = 5

# --- gating ----------------------------------------------------------------

# One phrase per line, matched case-insensitively as substrings. Kept as data
# files so the lists can be edited without touching code.
TTRPG_KEYWORDS_PATH = "./config/ttrpg_keywords.txt"
CLUB_KEYWORDS_PATH = "./config/club_keywords.txt"

# Generic social/wiki/review sites: they rank well but are rarely a club page.
EXCLUDED_DOMAINS_PATH = "./config/excluded_webpages.txt"


def _load_lines(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        lines = (line.strip() for line in f)
        return [line for line in lines if line and not line.startswith("#")]


def load_word_list(path: str) -> list[str]:
    """Read a file into a lowercased list, one entry per line, ignoring
    blanks and #-comments. Used for keyword lists and the excluded-domain
    list alike — both are simple line-delimited data.
    """
    return [line.lower() for line in _load_lines(path)]


def load_query_templates(path: str) -> list[str]:
    """Read query templates, preserving case (they're sent to search as-is)."""
    return _load_lines(path)