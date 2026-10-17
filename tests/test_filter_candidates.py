import filter_candidates


def test_main_delegates_csv_paths_to_rule_based_filter(monkeypatch):
    calls = []
    monkeypatch.setattr(
        filter_candidates.rule_based_filtering,
        "run_rule_based_filter",
        lambda input_csv, output_csv: calls.append((input_csv, output_csv)),
    )

    filter_candidates.main("search.csv", "filtered.csv")

    assert calls == [("search.csv", "filtered.csv")]
