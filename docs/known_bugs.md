# Known bugs (code differs from intent)

This file lists places where the code at HEAD does not do what the tests or
design say it should. The docs under `docs/` describe the code as it is. Remove
an entry here when the bug is fixed.

| #   | Where                                            | What happens                                                                                                                 | What was intended                                           | Evidence                                                                                                                                                                         |
| --- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Stage 3 `render_candidates.output_fieldnames()`  | Passes `club_keywords_found_in_snippet` and `ttrpg_keywords_found_in_snippet` through to `rendered_results.csv`.             | Drop both debug columns.                                    | `tests/test_render_candidates.py::test_output_fieldnames_keep_decision_but_drop_keyword_debug_fields` and `::test_main_all_discards_skips_browser_and_omits_debug_columns` fail. |
| 2   | Stage 2 `rule_based_filtering.SEARCH_FIELDNAMES` | Does not include `result_score`, so `filtered_candidates.csv` and every later CSV lack it.                                   | Unclear. Earlier docs listed it as carried through.         | `result_score` is written by Stage 1 but absent from Stage 2 output.                                                                                                             |
| 3   | `tests/test_search_providers.py`                 | Imports `search_providers` and `tavily_search_provider`, which no longer exist, so a plain `pytest` run fails at collection. | Deferred: fix or delete later. The file is kept on purpose. | Run `pytest` with `--ignore=tests/test_search_providers.py` for now.                                                                                                             |

Bug 2 also makes Stage 3's test fixture write a `result_score` that `DictWriter`
rejects, which is why the second failing test in bug 1 errors out.
