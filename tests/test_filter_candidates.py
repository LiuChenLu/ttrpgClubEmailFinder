import pytest

from filter_candidates import decide


KEYWORDS_WITH_ALL_GATES_PASSED = {
    "club_keywords_found_in_snippet": "club",
    "ttrpg_keywords_found_in_snippet": "tabletop",
    "club_keywords_found_in_page": "club",
    "ttrpg_keywords_found_in_page": "tabletop",
}


@pytest.mark.parametrize(
    "url",
    [
        "https://www.school.com/lunch_menu.pdf",
        "https://www.school.com/lunch_menu.PDF?download=1#page=2",
    ],
)
def test_pdf_result_is_discarded_even_when_keyword_gates_pass(url):
    row = {"result_url": url}

    assert decide(row, KEYWORDS_WITH_ALL_GATES_PASSED) == "discard"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.school.com/pdf-info/page",
        "https://www.school.com/lunch_menu.pdf-info",
        "https://www.school.com/club-page",
    ],
)
def test_non_pdf_result_remains_eligible_when_keyword_gates_pass(url):
    row = {"result_url": url}

    assert decide(row, KEYWORDS_WITH_ALL_GATES_PASSED) == "keep"