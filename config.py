"""Tunable constants shared by find_ttrpg_clubs.py and funnel_stats.py.

Has no dependency on the tavily package, so funnel_stats.py can import the
real thresholds instead of keeping a copy in sync by hand.
"""

DEFAULT_INPUT_CSV = "./data/search_institutions_sample.csv"
DEFAULT_RESULTS_CSV = "./data/ttrpg_clubs_search_results.csv"

# --- search ------------------------------------------------------------

# TODO: refine these placeholder queries.
QUERY_TEMPLATES = ["tabletop club {name}", "ttrpg {name}"]

MAX_RESULTS_PER_QUERY = 5

# Generic social/wiki/review sites: they rank well but are rarely a club page.
EXCLUDED_DOMAINS = [
    "facebook.com", "reddit.com", "instagram.com",
    "yelp.com", "wikipedia.org", "tiktok.com",
]

# basic (default) / fast / ultra-fast trade relevance for latency at 1 credit;
# advanced is the most relevant at 2 credits.
SEARCH_DEPTH = "advanced"

SLEEP_BETWEEN_COLLEGES_S = 0.2

# How many colleges (in input order) get a raw_content preview logged. Enough
# to catch a JS/consent-wall stub early in a run without hundreds of log lines.
RAW_CONTENT_PREVIEW_COUNT = 5

# --- gating --------------------------------------------------------------

# Minimum Tavily relevance score (0-1) before we pay to extract a page. Value
# is from Tavily's docs example; recorded per row as passed_score_gate so it
# can be checked against real score distributions via funnel_stats.py.
TAVILY_RELEVANCE_THRESHOLD = 0.7

# TODO: refine this keyword bag.
TTRPG_KEYWORDS = [
    "ttrpg", "tabletop", "dungeons and dragons", "dungeons & dragons", "d&d",
    "pathfinder", "dnd club", "role playing game", "roleplaying game",
    "game master", "dungeon master",
]

# --- CSV output ------------------------------------------------------------

SNIPPET_CHARS = 300

# --- funnel diagnostics ----------------------------------------------------

# Below this raw_content length, a "succeeded but no contact signal" row isn't
# worth hand-inspecting: more likely a thin/irrelevant page than a missed email.
HAND_INSPECT_MIN_LENGTH = 200