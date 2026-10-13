import pandas as pd
import pytest

import build_institution_dataset


@pytest.mark.parametrize(
    ("raw_aliases", "expected"),
    [
        ("First Alias; Second Alias", "First Alias|Second Alias"),
        ("First Alias,Second Alias", "First Alias|Second Alias"),
        ("First Alias | Second Alias", "First Alias|Second Alias"),
        ("UH System / UH", "UH System|UH"),
        ("'UH System/UH'", "'UH System|UH'"),
        (
            "Southern Christian University  Regions University",
            "Southern Christian University|Regions University",
        ),
        ("First Alias\tSecond Alias", "First Alias|Second Alias"),
        ("First Alias\nSecond Alias", "First Alias|Second Alias"),
        ("First Alias\rSecond Alias", "First Alias|Second Alias"),
        ("First Alias\fSecond Alias", "First Alias|Second Alias"),
        ("First Alias\vSecond Alias", "First Alias|Second Alias"),
        ("  First Alias  ", "First Alias"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_aliases(raw_aliases, expected):
    assert build_institution_dataset.normalize_aliases(raw_aliases) == expected


@pytest.mark.parametrize(
    ("name", "existing", "expected"),
    [
        ("University of Richmond", "", "Richmond"),
        ("Faulkner University", "", "Faulkner"),
        ("Bethany College", "", "Bethany"),
        (
            "Appalachian University of Art",
            "",
            "Appalachian University|Appalachian",
        ),
        ("Mass Bay Community College", "", "Mass Bay"),
        ("St. John", "", "St John"),
        (
            "A.T. Still University",
            "",
            "A.T. Still|AT Still University|AT Still",
        ),
        (
            "Massachusetts Jacobs University",
            "",
            "Massachusetts Jacobs|Mass Jacobs University|Mass Jacobs",
        ),
        (
            "Bethany College",
            "Bethany|Bethany College",
            "",
        ),
        (
            "Mass Bay Community College",
            "Mass Bay Downtown Campus",
            "Mass Bay",
        ),
        (
            "Faulkner University",
            "FAULKNER",
            "",
        ),
        ("University of Richmond", None, "Richmond"),
    ],
)
def test_generate_aliases(name, existing, expected):
    assert build_institution_dataset.generate_aliases(name, existing) == expected


def test_process_ipeds_filters_on_alias_and_exports_aliases(monkeypatch, capsys):
    monkeypatch.setattr(
        build_institution_dataset, "load_word_list", lambda _path: ["cosmetology"]
    )
    df = pd.DataFrame(
        [
            {
                "UNITID": 1,
                "INSTNM": "Example College",
                "IALIAS": "Cosmetology Training Institute",
                "CITY": "Town",
                "LONGITUD": -72.7,
                "LATITUDE": 41.8,
                "WEBADDR": "https://example.edu",
                "CYACTIVE": 1,
                "SECTOR": 1,
                "ICLEVEL": 1,
                "FTE": 400,
            },
            {
                "UNITID": 2,
                "INSTNM": "Another College",
                "IALIAS": "Former College Name",
                "CITY": "City",
                "LONGITUD": -72.8,
                "LATITUDE": 41.9,
                "WEBADDR": "https://another.edu",
                "CYACTIVE": 1,
                "SECTOR": 1,
                "ICLEVEL": 1,
                "FTE": 400,
            },
        ]
    )

    result = build_institution_dataset.process_ipeds(df)

    assert result["unitid"].tolist() == [2]
    assert result["aliases"].tolist() == ["Former College Name"]
    assert result["generated_aliases"].tolist() == ["Another"]
    assert result.columns.tolist() == [
        "unitid", "college_name", "aliases", "generated_aliases", "city",
        "distance", "website",
    ]
    assert "Kept rows with aliases: 1 of 1" in capsys.readouterr().out
