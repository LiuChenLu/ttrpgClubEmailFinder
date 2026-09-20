import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_DIR = PROJECT_ROOT / "ttrpgClubEmailFinder"
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from search_providers import SearchProvider, get_search_provider
from tavily_search_provider import QUERY_TEMPLATES_PATH, TavilySearchProvider


def test_provider_factory_returns_tavily_adapter():
    provider = get_search_provider("tavily")
    assert isinstance(provider, TavilySearchProvider)


def test_provider_contract_is_defined():
    assert hasattr(SearchProvider, "search")
    assert hasattr(SearchProvider, "extract")


def test_tavily_provider_owns_query_template_path():
    assert QUERY_TEMPLATES_PATH == "./config/query_templates.txt"
