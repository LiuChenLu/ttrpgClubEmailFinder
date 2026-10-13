import csv

import fetch_candidates
from fetch_candidates import SearchResult


def test_main_carries_alias_columns_from_institution_input(tmp_path, monkeypatch):
    input_csv = tmp_path / "institutions.csv"
    output_csv = tmp_path / "search_results.csv"
    with input_csv.open("w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(
            f_out,
            fieldnames=[
                "unitid", "college_name", "aliases", "generated_aliases",
                "city", "distance", "website",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "unitid": "1",
            "college_name": "Example College",
            "aliases": "Example U",
            "generated_aliases": "Example",
            "city": "Town",
            "distance": "20",
            "website": "https://example.edu",
        })

    monkeypatch.setattr(fetch_candidates, "load_query_templates", lambda _: ["{name} club"])
    monkeypatch.setattr(fetch_candidates, "load_word_list", lambda _: [])
    monkeypatch.setattr(fetch_candidates, "SLEEP_BETWEEN_COLLEGES_S", 0)
    monkeypatch.setattr(
        fetch_candidates,
        "search_college",
        lambda *args: (
            [
                SearchResult(
                    query="Example College club",
                    url="https://example.edu/club",
                    title="Tabletop Club",
                    score=0.9,
                    snippets=["Join our club"],
                    raw_content="Club page",
                    raw_content_status=fetch_candidates.RawStatus.SUCCEEDED,
                )
            ],
            [],
        ),
    )

    fetch_candidates.main(str(input_csv), str(output_csv))

    with output_csv.open(newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        rows = list(reader)

    assert "aliases" in reader.fieldnames
    assert "generated_aliases" in reader.fieldnames
    assert "distance" not in reader.fieldnames
    assert rows[0]["aliases"] == "Example U"
    assert rows[0]["generated_aliases"] == "Example"
