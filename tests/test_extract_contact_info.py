import csv

import extract_contact_info


INPUT_FIELDS = [
    "decision", "unitid", "college_name", "aliases", "generated_aliases",
    "result_url", "result_snippet",
    "result_raw_content", "content_source",
]


def test_main_scans_keeps_and_preserves_all_rendered_rows(tmp_path):
    input_csv = tmp_path / "rendered_results.csv"
    output_csv = tmp_path / "contacts.csv"
    rows = [
        {
            "decision": "keep",
            "unitid": "1",
            "college_name": "Example College",
            "aliases": "Example U",
            "generated_aliases": "Example",
            "result_url": "https://example.edu/club",
            "result_snippet": "Email club@example.edu",
            "result_raw_content": "Contact us at club@example.edu or discord.gg/club123",
            "content_source": "search",
        },
        {
            "decision": "discard",
            "unitid": "2",
            "college_name": "Other College",
            "aliases": "",
            "generated_aliases": "",
            "result_url": "https://other.edu/page",
            "result_snippet": "Email discard@example.edu",
            "result_raw_content": "Contact discard@example.edu",
            "content_source": "search",
        },
    ]
    with input_csv.open("w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=INPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    extract_contact_info.main(str(input_csv), str(output_csv))

    with output_csv.open(newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        result_rows = list(reader)

    assert reader.fieldnames == INPUT_FIELDS + extract_contact_info.NEW_FIELDNAMES
    assert [row["decision"] for row in result_rows] == ["keep", "discard"]
    assert result_rows[0]["has_contact_signal"] == "True"
    assert result_rows[0]["aliases"] == "Example U"
    assert result_rows[0]["generated_aliases"] == "Example"
    assert result_rows[0]["email_found"] == "club@example.edu"
    assert result_rows[0]["discord_found"] == "discord.gg/club123"
    assert result_rows[1]["has_contact_signal"] == "False"
    assert result_rows[1]["email_found"] == ""
