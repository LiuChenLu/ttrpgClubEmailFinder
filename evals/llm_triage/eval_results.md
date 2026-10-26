# Eval results

## Gemini 3.5-flash-lite, temperature 0, thinking_level medium

47 rows, 26 in the gate; 11 wrong ->
/home/liu/Documents/GitHub/ttrpgClubEmailFinder/evals/llm_triage/wrong.csv

- false_drop: 1 (gate 0)
- missed_drop: 3 (gate 0)
- label_only: 6 (gate 5)
- call_failed: 0 (gate 0)

Notes:

- false drop dropped an "ambigous" row, so it's not a missed drop.
- The missed drops all would have been dropped by rule_based_filtering.py.

Token usage on eval set: 276270 total, 86062 cached (31%)

## Gemini 3.5-flash-lite, temperature 0, thinking_level low

47 rows, 26 in the gate; 17 wrong ->
/home/liu/Documents/GitHub/ttrpgClubEmailFinder/evals/llm_triage/wrong.csv

- false_drop: 3 (gate 0)
- missed_drop: 8 (gate 0)
- label_only: 6 (gate 6)
- call_failed: 0 (gate 0)

Notes:

- false dropped some sister campus and the "ambiguous" row
- missed drops al would have been dropped by rule_based_filtering.py.

Token usage on eval set: 251261 total, 84192 cached (33%)
