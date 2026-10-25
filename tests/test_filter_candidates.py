import filter_candidates


def test_main_runs_rule_based_filter_then_llm_triage_on_its_output(monkeypatch):
    calls = []
    monkeypatch.setattr(
        filter_candidates.rule_based_filtering,
        "run_rule_based_filter",
        lambda input_csv, output_csv: calls.append(
            ("rules", input_csv, output_csv)
        ),
    )
    monkeypatch.setattr(
        filter_candidates.llm_triage,
        "run_llm_triage",
        lambda input_csv, output_csv, cache_only, note: calls.append(
            ("triage", input_csv, output_csv, cache_only, note)
        ),
    )

    filter_candidates.main("search.csv", "filtered.csv", "llm_filtered.csv")

    assert calls == [
        ("rules", "search.csv", "filtered.csv"),
        ("triage", "filtered.csv", "llm_filtered.csv", False, None),
    ]
