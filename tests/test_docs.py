"""Keeps the docs and the code from drifting apart. Offline, reads only files."""

import re
from pathlib import Path

import pytest

import schema

ROOT = Path(__file__).resolve().parent.parent
MARKDOWN_FILES = sorted(
    p for p in ROOT.rglob("*.md")
    if not {".venv", ".git", "data", "tmp", "node_modules"} & set(p.relative_to(ROOT).parts)
)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


def stage_columns_in_data_flow():
    """Map stage number to the backticked column names of its bullet lines."""
    text = (ROOT / "docs" / "data_flow.md").read_text(encoding="utf-8")
    columns = {}
    stage = None
    for line in text.splitlines():
        heading = re.match(r"## Stage (\d+b?)", line)
        if heading:
            stage = heading.group(1)
            stage = int(stage) if stage.isdigit() else stage
            columns[stage] = []
            continue
        bullet = re.match(r"- `([a-z_]+)`", line)
        if stage is not None and bullet:
            columns[stage].append(bullet.group(1))
    return columns


def introduced_by_stage():
    stage0 = schema.INSTITUTION_FIELDNAMES
    stage1 = [c for c in schema.SEARCH_RESULTS_FIELDNAMES if c not in stage0]
    stage2 = ["decision", *schema.KEYWORD_FIELDNAMES]
    return {
        0: stage0,
        1: stage1,
        2: stage2,
        "2b": schema.TRIAGE_NEW_FIELDNAMES,
        3: schema.RENDERED_NEW_FIELDNAMES,
        4: schema.CONTACT_NEW_FIELDNAMES,
    }


def test_data_flow_lists_each_column_under_the_stage_that_adds_it():
    documented = stage_columns_in_data_flow()
    expected = introduced_by_stage()

    assert {s: sorted(c) for s, c in documented.items()} == {
        s: sorted(c) for s, c in expected.items()
    }


def test_data_flow_lists_no_column_twice():
    documented = [c for cols in stage_columns_in_data_flow().values() for c in cols]

    assert len(documented) == len(set(documented))


def test_schema_chain_matches_what_each_stage_says_it_drops_and_adds():
    assert schema.SEARCH_RESULTS_FIELDNAMES[0] == "unitid"
    assert "distance" not in schema.SEARCH_RESULTS_FIELDNAMES
    assert schema.FILTERED_FIELDNAMES[0] == "decision"
    assert schema.RENDERED_FIELDNAMES[-2:] == ["render_status", "content_source"]
    assert schema.CONTACT_FIELDNAMES[-3:] == schema.CONTACT_NEW_FIELDNAMES


@pytest.mark.parametrize(
    "path", MARKDOWN_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_relative_markdown_links_resolve(path):
    text = CODE_FENCE_RE.sub("", path.read_text(encoding="utf-8"))
    broken = []
    for target in LINK_RE.findall(text):
        if re.match(r"[a-z]+:", target) or target.startswith("#"):
            continue
        file_part = target.split("#", 1)[0]
        if file_part and not (path.parent / file_part).exists():
            broken.append(target)

    assert not broken, f"{path.relative_to(ROOT)} has broken links: {broken}"


def test_every_config_constant_path_points_at_a_file_that_exists():
    import config

    missing = [
        f"{name}={value}"
        for name, value in vars(config).items()
        if name.endswith("_PATH") and name.startswith(("EXCLUDED", "QUERY", "TTRPG", "CLUB"))
        and not (ROOT / value).exists()
    ]

    assert not missing


def test_config_dir_holds_only_files_the_code_reads():
    import config

    read_by_code = {
        Path(v).name
        for k, v in vars(config).items()
        if k.endswith("_PATH") and isinstance(v, str) and v.startswith("./config/")
    }
    on_disk = {p.name for p in (ROOT / "config").iterdir()}

    assert on_disk == read_by_code
