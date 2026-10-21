"""The LLM call for Stage 2b, kept out of llm_triage.py on purpose.

llm_triage.py does all the pre and post processing and is deterministic. This
is the only place a model is called, so it can be stubbed or swapped without
touching that logic. llm_triage takes `label_result` as an argument, so tests
pass their own function.

Today `label_result` is a STUB: it makes no network call and returns STUB_VALUE
for every field of the response schema.

Has no dependency on google-genai, so importing it needs no API key.

TODO: replace the stub with a Gemini call. It should:
- build the prompt from config/triage_prompt.md and the few-shot examples, with
  the row input last,
- use TRIAGE_MODEL and TRIAGE_TEMPERATURE from config.py,
- request structured output with the fields in TRIAGE_LABEL_FIELDNAMES,
- retry 429 and 5xx responses with backoff,
- build the client lazily, like tavily_client_util.tavily(), so importing this
  module doesn't need the API key.
"""

from __future__ import annotations

from schema import STUB_VALUE, TRIAGE_LABEL_FIELDNAMES


def label_result(triage_input: dict) -> dict:
    """Label one search result.

    `triage_input` is built by llm_triage.build_triage_input. Returns one str
    per field in TRIAGE_LABEL_FIELDNAMES, and raises on any API failure.
    """
    return dict.fromkeys(TRIAGE_LABEL_FIELDNAMES, STUB_VALUE)
