import csv

import pytest

import render_candidates
from filter_candidates import FILTERED_FIELDNAMES
from render_candidates import ContentSource, ExtractStatus, output_fieldnames, render_row


def filtered_row(decision="discard"):
    return {
        "decision": decision,
        "unitid": "1",
        "college_name": "Example College",
        "aliases": "Example U",
        "generated_aliases": "Example",
        "city": "Town",
        "website": "https://example.edu",
        "search_query": "tabletop club",
        "result_title": "Tabletop Club",
        "result_url": "https://clubs.example.org/tabletop",
        "result_score": "0.9",
        "result_snippet": "Join the club",
        "raw_content_status": "empty",
        "raw_content_length": "0",
        "result_raw_content": "",
        "club_keywords_found_in_snippet": "club",
        "ttrpg_keywords_found_in_snippet": "tabletop",
    }


def test_output_fieldnames_keep_decision_but_drop_keyword_debug_fields():
    fields = output_fieldnames(FILTERED_FIELDNAMES)

    assert "decision" in fields
    assert "aliases" in fields
    assert "generated_aliases" in fields
    assert "club_keywords_found_in_snippet" not in fields
    assert "ttrpg_keywords_found_in_snippet" not in fields


def test_discard_row_skips_extract_and_playwright():
    row = filtered_row()

    def fail_if_called(*args):
        pytest.fail("discarded row must not be rendered")

    result = render_row(row, object(), fail_if_called)

    assert result["result_raw_content"] == ""
    assert result["extract_status"] == ""
    assert result["render_status"] == ""
    assert result["content_source"] == ""


def test_kept_blank_row_uses_extract_and_preserves_decision():
    row = filtered_row(decision="keep")
    result = render_row(
        row,
        object(),
        lambda url: (ExtractStatus.SUCCEEDED, "Contact tabletop@example.org"),
    )

    assert result["decision"] == "keep"
    assert result["result_raw_content"] == "Contact tabletop@example.org"
    assert result["content_source"] == ContentSource.EXTRACT
    assert result["render_status"] == render_candidates.RenderStatus.NOT_NEEDED


def test_main_all_discards_skips_browser_and_omits_debug_columns(tmp_path, monkeypatch):
    input_csv = tmp_path / "filtered_candidates.csv"
    output_csv = tmp_path / "rendered_results.csv"
    with input_csv.open("w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=FILTERED_FIELDNAMES)
        writer.writeheader()
        writer.writerow(filtered_row())

    def fail_browser_start():
        pytest.fail("all-discard input must not initialize Playwright")

    monkeypatch.setattr(render_candidates, "PlaywrightRenderer", fail_browser_start)
    render_candidates.main(str(input_csv), str(output_csv))

    with output_csv.open(newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        rows = list(reader)

    assert "decision" in reader.fieldnames
    assert "club_keywords_found_in_snippet" not in reader.fieldnames
    assert "ttrpg_keywords_found_in_snippet" not in reader.fieldnames
    assert len(rows) == 1
    assert rows[0]["decision"] == "discard"
    assert rows[0]["aliases"] == "Example U"
    assert rows[0]["generated_aliases"] == "Example"
    assert rows[0]["render_status"] == ""
