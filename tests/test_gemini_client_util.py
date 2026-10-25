"""Offline tests of the Stage 2b model call. The client is a fake, so no network
access or API key is needed. The live version is in
test_llm_triage_gemini_live_network.py.
"""

import json
from pathlib import Path

import pytest

import config
import gemini_client_util
import llm_triage
import schema

ROOT = Path(__file__).parent.parent
SPEC_SCHEMA = ROOT / "specs/stage2b_llm_triage/schema.json"

TRIAGE_INPUT = {
    "university": "Example College",
    "aliases": ["EC"],
    "url": "https://example.edu/clubs/tabletop",
    "title": "Tabletop Club | Example College",
    "domain_relation": "on_domain",
}


class FakeModels:
    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return type("Response", (), {"text": self.text})()


class FakeClient:
    def __init__(self, text=None, error=None):
        self.models = FakeModels(text, error)


def load_examples():
    path = ROOT / "config/llm_triage_examples.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_response_schema_matches_the_spec_schema_json():
    spec = json.loads(SPEC_SCHEMA.read_text(encoding="utf-8"))

    assert gemini_client_util.response_schema() == spec


def test_system_prompt_has_the_rubric_then_every_example():
    prompt = gemini_client_util.system_prompt()

    assert prompt.startswith("You label one web search result")
    assert prompt.index("## Examples") > prompt.index("## institution")
    for example in load_examples():
        assert json.dumps(example["input"], ensure_ascii=False) in prompt
        assert json.dumps(example["output"], ensure_ascii=False) in prompt


def test_every_example_is_valid_and_passes_the_evidence_check_unchanged():
    for example in load_examples():
        labels = llm_triage.validate_response(example["output"])

        assert llm_triage.check_evidence(labels, example["input"]) == labels


def test_label_result_sends_the_row_last_and_returns_the_parsed_reply():
    reply = {name: "" for name in schema.TRIAGE_LABEL_FIELDNAMES}
    client = FakeClient(text=json.dumps(reply))

    result = gemini_client_util.label_result(TRIAGE_INPUT, client)

    assert result == reply
    (call,) = client.models.calls
    assert call["model"] == config.TRIAGE_MODEL
    assert json.loads(call["contents"]) == TRIAGE_INPUT
    request = call["config"]
    assert request.system_instruction == gemini_client_util.system_prompt()
    assert request.temperature == config.TRIAGE_TEMPERATURE
    assert request.response_mime_type == "application/json"
    assert request.response_json_schema == gemini_client_util.response_schema()
    assert request.thinking_config.thinking_level.name == config.TRIAGE_THINKING_LEVEL


def test_build_request_holds_everything_the_model_sees_as_plain_json():
    request = gemini_client_util.build_request(TRIAGE_INPUT)

    assert request == {
        "model": config.TRIAGE_MODEL,
        "system_instruction": gemini_client_util.system_prompt(),
        "response_json_schema": gemini_client_util.response_schema(),
        "temperature": config.TRIAGE_TEMPERATURE,
        "thinking_level": config.TRIAGE_THINKING_LEVEL,
        "contents": json.dumps(TRIAGE_INPUT, ensure_ascii=False),
    }
    assert json.loads(json.dumps(request)) == request


def test_build_request_is_stable_and_changes_with_the_input():
    first = gemini_client_util.build_request(TRIAGE_INPUT)

    assert gemini_client_util.build_request(dict(TRIAGE_INPUT)) == first
    assert gemini_client_util.build_request({**TRIAGE_INPUT, "title": "Other"}) != first


def test_send_request_sends_only_what_the_dict_holds():
    client = FakeClient(text="{}")
    request = {
        **gemini_client_util.build_request(TRIAGE_INPUT),
        "model": "some-other-model",
        "temperature": 0.5,
        "thinking_level": "HIGH",
    }

    gemini_client_util.send_request(request, client)

    (call,) = client.models.calls
    assert call["model"] == "some-other-model"
    assert call["config"].temperature == 0.5
    assert call["config"].thinking_config.thinking_level.name == "HIGH"


@pytest.mark.parametrize("text", [None, "", "not json", "[1, 2]", '"a string"'])
def test_a_reply_that_is_not_a_json_object_comes_back_empty_to_be_retried(text):
    assert gemini_client_util.label_result(TRIAGE_INPUT, FakeClient(text=text)) == {}


def test_an_api_failure_is_raised_not_swallowed():
    client = FakeClient(error=TimeoutError("boom"))

    with pytest.raises(TimeoutError):
        gemini_client_util.label_result(TRIAGE_INPUT, client)


def test_an_api_failure_keeps_the_row_through_triage_row():
    def label_result(triage_input, attempt):
        return gemini_client_util.label_result(
            triage_input, FakeClient(error=TimeoutError("boom"))
        )

    result = llm_triage.triage_row(
        {
            "decision": "keep",
            "college_name": "Example College",
            "aliases": "",
            "website": "https://example.edu",
            "result_title": "Tabletop Club",
            "result_url": "https://example.edu/clubs",
            "search_query": "Example College gaming club",
        },
        label_result,
    )

    assert result["decision"] == "keep"
    assert result["triage_status"] == "api_error"


def test_passing_a_client_never_builds_the_shared_one(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    gemini_client_util.gemini.cache_clear()

    # Passing a client must never touch the API-key path either.
    gemini_client_util.label_result(TRIAGE_INPUT, FakeClient(text="{}"))

    assert gemini_client_util.gemini.cache_info().currsize == 0


def test_response_details_reads_text_finish_reason_and_every_usage_field():
    usage = type("Usage", (), {name: i for i, name in enumerate(
        schema.TRIAGE_USAGE_FIELDNAMES, start=1
    )})()
    candidate = type("Candidate", (), {"finish_reason": type("R", (), {"name": "STOP"})()})()
    response = type(
        "Response", (), {"text": "{}", "usage_metadata": usage, "candidates": [candidate]}
    )()

    details = gemini_client_util.response_details(response)

    assert details["raw_response"] == "{}"
    assert details["finish_reason"] == "STOP"
    assert [details[n] for n in schema.TRIAGE_USAGE_FIELDNAMES] == [1, 2, 3, 4, 5, 6]


def test_response_details_leaves_anything_missing_as_none():
    details = gemini_client_util.response_details(FakeModels(text="hi").generate_content())

    assert details["raw_response"] == "hi"
    assert details["finish_reason"] is None
    assert {details[n] for n in schema.TRIAGE_USAGE_FIELDNAMES} == {None}
