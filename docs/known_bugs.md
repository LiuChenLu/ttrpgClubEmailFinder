# Known bugs (code differs from intent)

This file lists places where the code at HEAD does not do what the tests or
design say it should. The docs under `docs/` describe the code as it is. Remove
an entry here when the bug is fixed.

| #   | Where                                            | What happens                                                                                                     | What was intended                                   | Evidence                                                                                                                                                                         |
| --- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Stage 2 `rule_based_filtering.SEARCH_FIELDNAMES` | Does not include `result_score`, so `filtered_candidates.csv` and every later CSV lack it.                       | Unclear. Earlier docs listed it as carried through. | `result_score` is written by Stage 1 but absent from Stage 2 output.                                                                                                             |

Bug 1 also makes Stage 3's test fixture write a `result_score` that `DictWriter`
rejects, so
`tests/test_render_candidates.py::test_main_all_discards_skips_browser_and_omits_debug_columns`
errors out.
