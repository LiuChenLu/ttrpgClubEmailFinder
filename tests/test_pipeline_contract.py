"""Runs Stages 1 to 4 on a few rows, offline, and checks each stage's output
against the column lists in schema.py. This is what catches a stage that stops
producing a column the next stage needs."""

import csv

import pytest

import extract_contact_info
import fetch_candidates
import render_candidates
import rule_based_filtering
import schema
from fetch_candidates import RawStatus, SearchResult

# Longer than config.SHORT_CONTENT_CHARS, so Stage 3 never needs Playwright.
LONG_PAGE = "Email club@example.edu or discord.gg/abc123. " + "Meets weekly. " * 100


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def write_institutions(path, n_colleges):
    with path.open("w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=schema.INSTITUTION_FIELDNAMES)
        writer.writeheader()
        for i in range(n_colleges):
            writer.writerow({
                "unitid": str(i), "college_name": f"College {i}",
                "aliases": "Example U", "generated_aliases": "Example",
                "city": "Town", "distance": "20", "website": "https://example.edu",
            })


class FakeRenderer:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None

    def fetch_text(self, url):
        pytest.fail("every kept row has long content, so nothing needs rendering")


@pytest.fixture
def pipeline_outputs(tmp_path, monkeypatch):
    institutions = tmp_path / "institutions.csv"
    write_institutions(institutions, 1)

    hits = [
        ("https://example.edu/clubs/tabletop", "Tabletop Club", "Join us", LONG_PAGE),
        ("https://example.edu/files/guide.pdf", "Tabletop Club guide", "Join us", LONG_PAGE),
        ("https://example.edu/dining", "Dining hall", "Lunch menu", LONG_PAGE),
    ]
    monkeypatch.setattr(fetch_candidates, "load_query_templates", lambda _: ["{name} club"])
    monkeypatch.setattr(fetch_candidates, "load_word_list", lambda _: [])
    monkeypatch.setattr(fetch_candidates, "SLEEP_BETWEEN_COLLEGES_S", 0)
    monkeypatch.setattr(
        fetch_candidates,
        "search_college",
        lambda *args: (
            [
                SearchResult(
                    query="College 0 club", url=url, title=title,
                    score=0.9, snippets=[snippet], raw_content=text,
                    raw_content_status=RawStatus.SUCCEEDED,
                )
                for url, title, snippet, text in hits
            ],
            [],
        ),
    )
    monkeypatch.setattr(
        rule_based_filtering, "load_keyword_lists",
        lambda: rule_based_filtering.KeywordLists(ttrpg=["tabletop"], club=["club"]),
    )
    monkeypatch.setattr(render_candidates, "PlaywrightRenderer", FakeRenderer)

    paths = {
        name: tmp_path / f"{name}.csv"
        for name in ("search", "filtered", "rendered", "contacts")
    }
    fetch_candidates.main(str(institutions), str(paths["search"]))
    rule_based_filtering.run_rule_based_filter(
        str(paths["search"]), str(paths["filtered"])
    )
    render_candidates.main(str(paths["filtered"]), str(paths["rendered"]))
    extract_contact_info.main(str(paths["rendered"]), str(paths["contacts"]))
    return paths


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("search", schema.SEARCH_RESULTS_FIELDNAMES),
        ("filtered", schema.FILTERED_FIELDNAMES),
        ("rendered", schema.RENDERED_FIELDNAMES),
        ("contacts", schema.CONTACT_FIELDNAMES),
    ],
)
def test_each_stage_writes_exactly_the_schema_columns(pipeline_outputs, name, expected):
    fieldnames, _ = read_csv(pipeline_outputs[name])

    assert fieldnames == expected


def test_decisions_survive_every_stage_and_only_keep_is_scanned(pipeline_outputs):
    _, rows = read_csv(pipeline_outputs["contacts"])

    assert [r["decision"] for r in rows] == [
        schema.KEEP,
        schema.discard_decision(schema.REASON_PDF),
        schema.discard_decision(schema.REASON_NO_KEYWORDS),
    ]
    assert [r["has_contact_signal"] for r in rows] == ["True", "False", "False"]
    assert rows[0]["email_found"] == "club@example.edu"
    assert rows[0]["discord_found"] == "discord.gg/abc123"


def test_every_decision_value_is_keep_or_a_known_discard_reason(pipeline_outputs):
    _, rows = read_csv(pipeline_outputs["filtered"])
    allowed = {schema.KEEP, *map(schema.discard_decision, schema.DISCARD_REASONS)}

    assert {r["decision"] for r in rows} <= allowed


def test_stage_two_drops_result_score_and_stage_three_drops_keyword_columns():
    assert "result_score" in schema.SEARCH_RESULTS_FIELDNAMES
    assert "result_score" not in schema.FILTERED_FIELDNAMES
    assert not set(schema.KEYWORD_FIELDNAMES) & set(schema.RENDERED_FIELDNAMES)


@pytest.fixture
def stub_search(monkeypatch):
    searched = []
    monkeypatch.setattr(fetch_candidates, "load_query_templates", lambda _: ["{name} club"])
    monkeypatch.setattr(fetch_candidates, "load_word_list", lambda _: [])
    monkeypatch.setattr(fetch_candidates, "SLEEP_BETWEEN_COLLEGES_S", 0)
    monkeypatch.setattr(
        fetch_candidates, "search_college",
        lambda name, *args: searched.append(name) or ([], []),
    )
    return searched


def test_fetch_refuses_a_run_over_the_credit_cap_without_yes(tmp_path, stub_search):
    institutions = tmp_path / "institutions.csv"
    write_institutions(institutions, 60)
    output = tmp_path / "out.csv"
    output.write_text("previous output\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="--yes"):
        fetch_candidates.main(str(institutions), str(output))

    assert stub_search == []
    assert output.read_text(encoding="utf-8") == "previous output\n"


def test_fetch_yes_overrides_the_credit_cap(tmp_path, stub_search):
    institutions = tmp_path / "institutions.csv"
    write_institutions(institutions, 60)

    fetch_candidates.main(
        str(institutions), str(tmp_path / "out.csv"), assume_yes=True
    )

    assert len(stub_search) == 60


def test_fetch_limit_caps_colleges_below_the_credit_cap(tmp_path, stub_search):
    institutions = tmp_path / "institutions.csv"
    write_institutions(institutions, 60)

    fetch_candidates.main(str(institutions), str(tmp_path / "out.csv"), limit=3)

    assert stub_search == ["College 0", "College 1", "College 2"]
