"""Tunable constants shared by the pipeline scripts.

Has no dependency on the tavily package, and reads no files at import time, so
any consumer can import the real thresholds without an API key or the data
files present.
"""

# Output of stage 0
INSTITUTIONS_CSV = "./data/institutions.csv"

# A very small collection of IPEDS institutions that have TTRPG clubs. Stage 1
# reads this by default so a plain run is cheap. Use `--input` to point it at
# INSTITUTIONS_CSV for a full run.
HAS_TTRPG_CLUB_PATH = "./data/iped_institution_has_ttrpg_club.csv"
DEFAULT_INPUT_CSV = HAS_TTRPG_CLUB_PATH

# Output of stage 1
SEARCH_RESULTS_CSV = "./data/search_results.csv"
# Output of stage 2
DEFAULT_FILTERED_CSV = "./data/filtered_candidates.csv"
# Output of stage 3
RENDERED_RESULTS_CSV = "./data/rendered_results.csv"
# Output of stage 4
DEFAULT_CONTACTS_CSV = "./data/ttrpg_clubs_contacts.csv"

# --- institutions (stage 0) -------------------------------------------------

IPEDS_DB_PATH = "./data/ipeds/IPEDS_2024-25_Provisional/IPEDS202425.accdb"
IPEDS_HD_TABLE = "HD2024"
IPEDS_ENROLLMENT_TABLE = "DRVEF2024"
IPEDS_SIZE_COLUMN = "FTE"

# Minimum FTE by IPEDS ICLEVEL. Level 3's minimum is set high enough to drop
# every level 3 (under 2 year) institution.
SIZE_MINIMUMS = {1: 300, 2: 750, 3: 10000}

# An institution whose name or alias matches EXCLUDED_INSTITUTION_NAMES_PATH is
# dropped only if its FTE is below this.
KEYWORD_SIZE_MAXIMUM = 1500

# Stage 0 computes each campus's distance from Hartford, CT.
HARTFORD_LATITUDE = 41.763710
HARTFORD_LONGITUDE = -72.685097

# One term per line, matched as whole words, case-insensitively, against the
# institution name and its aliases. Drops school types that won't have a TTRPG
# club (beauty, cosmetology, etc.).
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

# Stage 1 refuses to start a run estimated above this many Tavily credits unless
# the user passes --yes. The estimate is searches x credits per search.
MAX_UNCONFIRMED_SEARCH_CREDITS = 100

# Tavily only honors this when the search topic is "general" (its default).
SEARCH_COUNTRY = "united states"

# Page-text format for both the search hit's raw_content and Stage 3's
# fallback extract().
RAW_CONTENT_FORMAT = "markdown"

SLEEP_BETWEEN_COLLEGES_S = 0.2

# How many colleges (in input order) get a raw_content preview logged. Enough
# to catch a JS/consent-wall stub early in a run without hundreds of log lines.
RAW_CONTENT_PREVIEW_COUNT = 5

# --- render (stage 3) --------------------------------------------------------

EXTRACT_DEPTH = "advanced"
EXTRACT_MAX_ATTEMPTS = 2
EXTRACT_RETRY_SLEEP_S = 2

# Non-blank page text shorter than this on a .edu URL may be a JS stub, so it is
# re-fetched with Playwright.
SHORT_CONTENT_CHARS = 1000

# Per-page limit for Playwright's goto() and inner_text().
PLAYWRIGHT_TIMEOUT_MS = 30_000

# Number of browser deaths in a row that abort the run. Each death relaunches
# Chromium and marks that URL failed; without a cap, a systemic problem (out of
# memory, a broken install) would silently mark every remaining row failed. A 
# Playwright call that ends with the browser still alive resets the count.
PLAYWRIGHT_MAX_CONSECUTIVE_CRASHES = 3

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