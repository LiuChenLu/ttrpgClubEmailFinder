import csv

import pytest

from filter_candidates import (
    FILTERED_FIELDNAMES, SEARCH_FIELDNAMES, main,
)
from rule_based_filtering import decide


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


@pytest.mark.parametrize(
    "term",
    [
        "blog", "news", "article", "dailydigest", "stories", "story",
        "rsvp", "event", "calendar",
        "store", "shop", "market",
    ],
)
def test_low_relevance_url_types_are_discarded_even_when_keyword_gates_pass(term):
    row = {"result_url": f"https://www.school.com/{term}/club"}

    assert decide(row, KEYWORDS_WITH_ALL_GATES_PASSED) == "discard"


def test_url_filtering_is_case_insensitive():
    row = {"result_url": "https://www.school.com/News/club"}

    assert decide(row, KEYWORDS_WITH_ALL_GATES_PASSED) == "discard"


def test_main_preserves_search_rows_and_writes_keyword_audit(tmp_path):
    input_csv = tmp_path / "search_results.csv"
    output_csv = tmp_path / "filtered_candidates.csv"
    rows = [
        {
            "unitid": "1", "college_name": "Example College", "city": "Town",
            "aliases": "Example U", "generated_aliases": "Example",
            "website": "https://example.edu", "search_query": "club search",
            "result_title": "Tabletop Gaming Club", "result_url": "https://example.edu/club",
            "result_score": "0.9", "result_snippet": "Join our club",
            "raw_content_status": "succeeded", "raw_content_length": "12",
            "result_raw_content": "search page text",
        },
        {
            "unitid": "2", "college_name": "Other College", "city": "Town",
            "aliases": "", "generated_aliases": "",
            "website": "https://other.edu", "search_query": "other search",
            "result_title": "Dining schedule", "result_url": "https://other.edu/dining",
            "result_score": "0.2", "result_snippet": "Dining hall hours",
            "raw_content_status": "succeeded", "raw_content_length": "8",
            "result_raw_content": "dining page",
        },
        {
            "unitid": "3", "college_name": "No Results College", "city": "Town",
            "aliases": "No Results U", "generated_aliases": "No Results",
            "website": "https://none.edu", "search_query": "NO_RESULTS: tabletop club",
            "result_title": "", "result_url": "", "result_score": "",
            "result_snippet": "", "raw_content_status": "", "raw_content_length": "",
            "result_raw_content": "",
        },
    ]
    with input_csv.open("w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=SEARCH_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    main(str(input_csv), str(output_csv))

    with output_csv.open(newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        result_rows = list(reader)
        assert reader.fieldnames == FILTERED_FIELDNAMES

    assert [row["decision"] for row in result_rows] == ["keep", "discard", "discard"]
    assert result_rows[0]["search_query"] == rows[0]["search_query"]
    assert result_rows[0]["aliases"] == rows[0]["aliases"]
    assert result_rows[0]["generated_aliases"] == rows[0]["generated_aliases"]
    assert result_rows[0]["result_raw_content"] == rows[0]["result_raw_content"]
    assert result_rows[0]["club_keywords_found_in_snippet"]
    assert result_rows[0]["ttrpg_keywords_found_in_snippet"]