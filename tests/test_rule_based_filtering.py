import csv

import pytest

import rule_based_filtering as filtering
import schema
from search_row_format_util import is_sentinel


@pytest.fixture
def keyword_lists():
    return filtering.KeywordLists(ttrpg=["tabletop"], club=["gaming club"])


def make_row(**overrides):
    row = {
        "unitid": "1",
        "college_name": "Example College",
        "aliases": "",
        "generated_aliases": "",
        "city": "Town",
        "website": "https://example.edu",
        "search_query": "Example College gaming club",
        "result_title": "",
        "result_url": "https://example.edu/clubs",
        "result_snippet": "",
        "raw_content_status": "succeeded",
        "raw_content_length": "0",
        "result_raw_content": "",
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("text", "keywords", "expected"),
    [
        ("Join the TABLETOP group", ["tabletop"], ["tabletop"]),
        ("Gaming club information", ["gaming club"], ["gaming club"]),
        ("no matching phrase", ["tabletop", "gaming club"], []),
        ("regex characters .* stay literal", [".*"], [".*"]),
    ],
)
def test_find_keywords_uses_case_insensitive_literal_substrings(
    text, keywords, expected
):
    assert filtering.find_keywords(text, keywords) == expected


@pytest.mark.parametrize("url", ["", "ERROR"])
def test_is_sentinel_detects_missing_result_url(url):
    assert is_sentinel({"result_url": url})


def test_is_sentinel_does_not_mark_regular_result_as_sentinel():
    assert not is_sentinel({"result_url": "https://example.edu/club"})


@pytest.mark.parametrize(
    ("url", "expected_reason"),
    [
        ("https://example.edu/files/guide.PDF?download=1", "pdf"),
        ("https://example.edu/NEWS/club", "news"),
        ("https://example.edu/calendar/club", "event"),
        ("https://example.edu/shop/club", "storefronts"),
        ("https://example.edu/clubs/tabletop", None),
        ("https://example.edu/not-a.pdf-page", None),
    ],
)
def test_url_filtering_reason(url, expected_reason):
    assert filtering.url_filtering_reason(url) == expected_reason


def test_keyword_columns_match_title_and_snippet_not_page_text(keyword_lists):
    row = make_row(
        result_title="Gaming Club",
        result_snippet="A tabletop group",
        result_raw_content="unrelated",
    )

    assert filtering.keyword_columns(
        row, keyword_lists.ttrpg, keyword_lists.club
    ) == {
        "club_keywords_found_in_snippet": "gaming club",
        "ttrpg_keywords_found_in_snippet": "tabletop",
    }


def test_keyword_columns_skip_sentinel_error_message(keyword_lists):
    row = make_row(result_url="ERROR", result_title="Tabletop gaming club failed")

    assert filtering.keyword_columns(
        row, keyword_lists.ttrpg, keyword_lists.club
    ) == {
        "club_keywords_found_in_snippet": "",
        "ttrpg_keywords_found_in_snippet": "",
    }


@pytest.mark.parametrize(
    ("row", "keywords", "expected_reason"),
    [
        (make_row(result_url=""), {}, schema.REASON_SENTINEL_ROW),
        (make_row(result_url="https://example.edu/file.pdf"), {}, "pdf"),
        (
            make_row(result_url="https://example.edu/news"),
            {},
            "news",
        ),
        (
            make_row(),
            {
                "club_keywords_found_in_snippet": "",
                "ttrpg_keywords_found_in_snippet": "",
            },
            schema.REASON_NO_KEYWORDS,
        ),
        (
            make_row(),
            {
                "club_keywords_found_in_snippet": "gaming club",
                "ttrpg_keywords_found_in_snippet": "",
            },
            None,
        ),
    ],
)
def test_discard_reason(row, keywords, expected_reason):
    assert filtering.discard_reason(row, keywords) == expected_reason


def test_apply_rules_returns_decision_and_keyword_evidence(keyword_lists):
    result = filtering.apply_rules(
        make_row(result_title="Tabletop gaming club"), keyword_lists
    )

    assert result == {
        "decision": "keep",
        "club_keywords_found_in_snippet": "gaming club",
        "ttrpg_keywords_found_in_snippet": "tabletop",
    }


def test_apply_rules_writes_the_full_discard_decision(keyword_lists):
    result = filtering.apply_rules(
        make_row(result_title="Dining hall"), keyword_lists
    )

    assert result == {
        "decision": "discard_snippets_has_no_club_or_ttrpg_keywords",
        "club_keywords_found_in_snippet": "",
        "ttrpg_keywords_found_in_snippet": "",
    }


def write_search_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=filtering.SEARCH_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def test_run_rule_based_filter_writes_rows_decisions_and_reason_counts(
    tmp_path, monkeypatch, capsys, keyword_lists
):
    input_csv = tmp_path / "search_results.csv"
    output_csv = tmp_path / "filtered_candidates.csv"
    rows = [
        make_row(
            unitid="1",
            result_title="Tabletop gaming club",
            result_snippet="Join the group",
        ),
        make_row(
            unitid="2",
            result_url="https://example.edu/files/guide.pdf",
            result_title="Tabletop club",
        ),
        make_row(
            unitid="3",
            result_url="https://example.edu/news/club",
            result_title="Tabletop club",
        ),
        make_row(
            unitid="4",
            result_title="Dining hall",
        ),
        make_row(unitid="5", result_url="", result_title="Tabletop club"),
    ]
    write_search_csv(input_csv, rows)
    monkeypatch.setattr(filtering, "load_keyword_lists", lambda: keyword_lists)

    filtering.run_rule_based_filter(str(input_csv), str(output_csv))

    with output_csv.open(newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        result_rows = list(reader)
        assert reader.fieldnames == filtering.FILTERED_FIELDNAMES

    assert [row["decision"] for row in result_rows] == [
        "keep",
        "discard_pdf",
        "discard_news",
        "discard_snippets_has_no_club_or_ttrpg_keywords",
        "discard_sentinel_row",
    ]
    assert [row["unitid"] for row in result_rows] == ["1", "2", "3", "4", "5"]
    assert result_rows[0]["club_keywords_found_in_snippet"] == "gaming club"
    assert result_rows[0]["ttrpg_keywords_found_in_snippet"] == "tabletop"
    assert result_rows[0]["result_raw_content"] == rows[0]["result_raw_content"]

    output = capsys.readouterr().out
    assert "pdf: 1" in output
    assert "news: 1" in output
    assert "snippets_has_no_club_or_ttrpg_keywords: 1" in output
    assert "sentinel_row: 1" in output
    assert "event: 0" in output


def test_run_rule_based_filter_rejects_missing_columns_without_truncating_output(
    tmp_path, monkeypatch, keyword_lists
):
    input_csv = tmp_path / "incomplete.csv"
    output_csv = tmp_path / "existing.csv"
    input_csv.write_text("unitid,college_name\n1,Example College\n", encoding="utf-8")
    output_csv.write_text("previous output\n", encoding="utf-8")
    monkeypatch.setattr(filtering, "load_keyword_lists", lambda: keyword_lists)

    with pytest.raises(ValueError, match="is missing columns"):
        filtering.run_rule_based_filter(str(input_csv), str(output_csv))

    assert output_csv.read_text(encoding="utf-8") == "previous output\n"
