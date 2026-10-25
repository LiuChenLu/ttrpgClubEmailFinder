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


def build_request(triage_input: dict) -> dict:
    """Everything the model sees, as plain JSON values.

    `send_request` reads nothing but this dict, so a hash of it covers the whole
    call: a new setting can only reach the model by being added here. Plain
    values, not SDK types, so an SDK upgrade can't change the hash.
    """
    return {
        "model": TRIAGE_MODEL,
        "system_instruction": system_prompt(),
        "response_json_schema": response_schema(),
        "temperature": TRIAGE_TEMPERATURE,
        "thinking_level": TRIAGE_THINKING_LEVEL,
        "contents": json.dumps(triage_input, ensure_ascii=False),
    }


def send_request(request: dict, client: genai.Client | None = None):
    """Call Gemini with a `build_request` dict and return the SDK response.

    Raises on an API failure that the client's own retries (429 and 5xx)
    didn't clear. `client` is for tests; it defaults to the shared `gemini()`.
    """
    client = client or gemini()
    return client.models.generate_content(
        model=request["model"],
        contents=request["contents"],
        config=types.GenerateContentConfig(
            system_instruction=request["system_instruction"],
            temperature=request["temperature"],
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel[request["thinking_level"]]
            ),
            response_mime_type="application/json",
            response_json_schema=request["response_json_schema"],
        ),
    )


def parse_reply(text: str | None) -> dict:
    """The reply text as a dict. Anything that isn't a JSON object (blocked,
    empty, cut off) is {} so llm_triage retries it as invalid output.
    """
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def label_result(triage_input: dict, client: genai.Client | None = None) -> dict:
    """Label one search result.

    `triage_input` is built by llm_triage.build_triage_input. Returns the
    parsed reply, one str per field in TRIAGE_LABEL_FIELDNAMES when the model
    behaves, or {} (see `parse_reply`). Raises on an API failure.

    `client` is for tests; it defaults to the shared `gemini()` client.
    """
    response = send_request(build_request(triage_input), client)
    return parse_reply(response.text)
