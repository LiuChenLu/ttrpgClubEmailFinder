"""The LLM call for Stage 2b, kept out of llm_triage.py on purpose.

llm_triage.py does all the pre and post processing and is deterministic. This
is the only place a model is called, so it can be faked or swapped without
touching that logic. llm_triage takes `label_result` as an argument, so tests
pass their own function.

The client is built on first use and .env is read then, so importing this module
reads no files and needs no API key.
"""

from __future__ import annotations

import functools
import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from config import (
    TRIAGE_API_ATTEMPTS,
    TRIAGE_API_INITIAL_DELAY_S,
    TRIAGE_API_MAX_DELAY_S,
    TRIAGE_EXAMPLES_PATH,
    TRIAGE_MODEL,
    TRIAGE_PROMPT_PATH,
    TRIAGE_TEMPERATURE,
    TRIAGE_THINKING_LEVEL,
)
from schema import TRIAGE_ENUM_VALUES, TRIAGE_LABEL_FIELDNAMES

# Only these are retried by the client; any other API error is raised at once.
RETRY_STATUS_CODES = [429, 500, 502, 503, 504]


@functools.cache
def gemini() -> genai.Client:
    """Built lazily so importing this module doesn't require the API key."""
    load_dotenv()
    return genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(
                attempts=TRIAGE_API_ATTEMPTS,
                initial_delay=TRIAGE_API_INITIAL_DELAY_S,
                max_delay=TRIAGE_API_MAX_DELAY_S,
                http_status_codes=RETRY_STATUS_CODES,
            )
        ),
    )


def response_schema() -> dict:
    """The JSON schema of the model's reply, built from schema.py so the field
    list has one home. Property order is the order the model writes them in:
    evidence first, so it quotes the text before committing to a label.
    """
    properties = {
        name: (
            {"type": "string", "enum": list(TRIAGE_ENUM_VALUES[name])}
            if name in TRIAGE_ENUM_VALUES
            else {"type": "string"}
        )
        for name in TRIAGE_LABEL_FIELDNAMES
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(TRIAGE_LABEL_FIELDNAMES),
        "additionalProperties": False,
    }


@functools.cache
def system_prompt() -> str:
    """The rubric, then the few-shot examples. Identical for every row so the
    API can cache it; the row goes in `contents`, after it.
    """
    with open(TRIAGE_PROMPT_PATH, encoding="utf-8") as f:
        rubric = f.read().strip()
    with open(TRIAGE_EXAMPLES_PATH, encoding="utf-8") as f:
        examples = [json.loads(line) for line in f if line.strip()]
    shown = "\n\n".join(
        f"Input:\n{json.dumps(e['input'], ensure_ascii=False)}\n"
        f"Output:\n{json.dumps(e['output'], ensure_ascii=False)}"
        for e in examples
    )
    return f"{rubric}\n\n## Examples\n\n{shown}"


def label_result(triage_input: dict, client: genai.Client | None = None) -> dict:
    """Label one search result.

    `triage_input` is built by llm_triage.build_triage_input. Returns the
    parsed reply, one str per field in TRIAGE_LABEL_FIELDNAMES when the model
    behaves. A reply that isn't a JSON object (blocked, empty, cut off) comes
    back as {} so llm_triage retries it as invalid output. Raises on an API
    failure that the client's own retries (429 and 5xx) didn't clear.

    `client` is for tests; it defaults to the shared `gemini()` client.
    """
    client = client or gemini()
    response = client.models.generate_content(
        model=TRIAGE_MODEL,
        contents=json.dumps(triage_input, ensure_ascii=False),
        config=types.GenerateContentConfig(
            system_instruction=system_prompt(),
            temperature=TRIAGE_TEMPERATURE,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel[TRIAGE_THINKING_LEVEL]
            ),
            response_mime_type="application/json",
            response_json_schema=response_schema(),
        ),
    )
    try:
        parsed = json.loads(response.text)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
