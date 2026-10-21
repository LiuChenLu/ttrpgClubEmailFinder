import pytest

from url_parsing_utils import extract_host, registrable_domain


@pytest.mark.parametrize(
    "url, expected",
    [
        ("mit.edu", "mit.edu"),
        ("https://mit.edu", "mit.edu"),
        ("https://www.mit.edu", "www.mit.edu"),
        ("HTTPS://WWW.MIT.EDU/Clubs", "www.mit.edu"),
        ("https://mit.edu.", "mit.edu"),
        ("mit.edu:8080/a", "mit.edu"),
        ("http://mit.edu:443/a/b?x=1#frag", "mit.edu"),
        ("  https://mit.edu/  ", "mit.edu"),
        ("https://user:pw@mit.edu/", "mit.edu"),
        ("mit.edu?q=1", "mit.edu"),
    ],
)
def test_extract_host_normalizes(url, expected):
    assert extract_host(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        None,
        float("nan"),
        "",
        "   ",
        "https://",
        "https:///path",
        ".",
        "https://192.168.0.1/clubs",
        "10.0.0.1:8080",
        "https://[::1]/",
        "https://[bad/",
    ],
)
def test_extract_host_rejects_invalid_input_and_ip_addresses(url):
    assert extract_host(url) is None


@pytest.mark.parametrize(
    "url, expected",
    [
        ("mit.edu", "mit.edu"),
        ("https://www.mit.edu/x", "mit.edu"),
        ("www2.cortland.edu/", "cortland.edu"),
        ("https://hartford.uconn.edu/", "uconn.edu"),
        ("www.qcc.cuny.edu/", "cuny.edu"),
    ],
)
def test_registrable_domain_is_the_last_two_labels(url, expected):
    assert registrable_domain(url) == expected


@pytest.mark.parametrize("url", ["localhost", "https://localhost:3000", "a..edu", "", None])
def test_registrable_domain_is_none_without_two_labels(url):
    assert registrable_domain(url) is None
