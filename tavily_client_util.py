"""The Tavily client, shared by the Stage 1 and Stage 3 scripts.

Kept out of config.py on purpose: config.py has no dependency on the tavily
package and reads no files at import time, so any consumer can import the real
thresholds without an API key or the data files.

Importing this module loads .env.
"""

from __future__ import annotations

import functools
import os

from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()


@functools.cache
def tavily() -> TavilyClient:
    """Built lazily so importing this module doesn't require the API key."""
    return TavilyClient(api_key=os.environ["TAVILY_API_KEY"])