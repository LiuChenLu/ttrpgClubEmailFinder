"""URL host parsing shared by Stage 0 (`is_edu`) and Stage 2b (`is_on_domain`).

IPEDS WEBADDR values and search result URLs are inconsistent: with or without a
scheme, with or without "www.", sometimes with a port or a path. Everything here
works on the host alone. Pure functions; no files, no network.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

_SCHEME_RE = re.compile(r"^\w+://")


def extract_host(url: object) -> str | None:
    """The lowercase host of `url` without port or trailing dots, or None.

    Accepts "mit.edu", "www.mit.edu/x" and "https://MIT.edu.:443/x?y". None for
    anything that is not a string, has no host, can't be parsed, or whose host
    is an IP address (not supported, so callers treat it as no match).
    """
    if not isinstance(url, str):
        return None
    # urlsplit only finds the host after a leading "//", so a scheme-less URL
    # would otherwise be read as a path.
    text = _SCHEME_RE.sub("", url.strip().lower())
    try:
        host = urlsplit("//" + text).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.rstrip(".")
    if not host:
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    return None


def registrable_domain(url: object) -> str | None:
    """The last two labels of the host of `url` ("www.mit.edu" -> "mit.edu").

    None when there is no usable host, a single label, or an empty label.

    Assumes a one-label public suffix, which holds for `.edu` (all of Stage 0's
    institutions). It is wrong for suffixes like "co.uk"; adding the public
    suffix list as a dependency is not worth it for `.edu`.
    """
    host = extract_host(url)
    if host is None:
        return None
    labels = host.split(".")
    if len(labels) < 2 or not all(labels):
        return None
    return ".".join(labels[-2:])
