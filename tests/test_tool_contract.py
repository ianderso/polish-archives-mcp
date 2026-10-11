"""Contract tests over the registered MCP tool surface.

These assert properties of the tools *as a client sees them*: their names,
their JSON schema, their annotations, and the size of the description block
shipped on every session. The rest of the suite exercises the client and the
parsers, which means a ``Field`` typo or a dropped docstring could change the
published contract without failing a single test.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import respx
from mcp.server.mcpserver.exceptions import ToolError

from polish_archives_mcp import __version__, server
from polish_archives_mcp.server import mcp

from .conftest import assert_reached_body, call_tool, every_site, valid_args

SNAPSHOT = Path(__file__).parent / "fixtures" / "tool_schema.json"
README = Path(__file__).parent.parent / "README.md"

#: Ceiling on the combined tool descriptions, which are sent to the model on
#: every session before any work happens. Raise it deliberately, not by accident.
#: 0.1.0 ships about 2,550 characters.
DESCRIPTION_BUDGET = 2_900

#: Tools that touch no network at all.
LOCAL_TOOLS = {"regions", "cache_status"}

#: The one tool that writes anything, and only a new local file.
WRITES_LOCAL_FILE = {"swa_scan"}

#: Words that would mean a tool changes something somewhere.
WRITE_WORDS = re.compile(r"(^|_)(insert|update|edit|publish|delete|merge|add|create|write)(_|$)")


async def _tools() -> list:
    return sorted(await mcp.list_tools(), key=lambda t: t.name)


def _params(tool) -> dict:
    return (tool.input_schema or {}).get("properties", {}) or {}


async def test_every_tool_has_a_description():
    assert [t.name for t in await _tools() if not (t.description or "").strip()] == []


async def test_every_parameter_has_a_description():
    undocumented = [
        f"{t.name}.{name}"
        for t in await _tools()
        for name, spec in _params(t).items()
        if not (spec.get("description") or "").strip()
    ]
    assert undocumented == []


async def test_no_parameter_leaks_a_python_repr():
    leaked = [
        t.name
        for t in await _tools()
        if "FieldInfo" in json.dumps(t.input_schema)
        or "PydanticUndefined" in json.dumps(t.input_schema)
    ]
    assert leaked == []


async def test_tool_names_and_parameters_match_the_snapshot():
    """Renaming a tool or a parameter breaks callers; make it a visible diff.

    Regenerate deliberately with ``uv run python -m tests.regen_tool_snapshot``.
    """
    current = {t.name: sorted(_params(t)) for t in await _tools()}
    assert current == json.loads(SNAPSHOT.read_text())


async def test_every_tool_appears_in_the_readme_and_the_count_is_right():
    doc = README.read_text()
    names = {t.name for t in await _tools()}
    documented = set(re.findall(r"\| `([a-z_]+)`", doc))
    assert names <= documented, f"not in the README: {sorted(names - documented)}"
    assert documented - names == set(), (
        f"README documents removed tools: {sorted(documented - names)}"
    )
    words = {7: "seven"}
    assert f"publishes {words.get(len(names), len(names))} tools" in doc


async def test_description_block_stays_within_budget():
    total = sum(len(t.description or "") for t in await _tools())
    assert total <= DESCRIPTION_BUDGET, f"descriptions total {total}, over {DESCRIPTION_BUDGET}"


async def test_descriptions_ship_without_indentation_on_every_python():
    """Python 3.13 dedents docstrings and 3.11 and 3.12 do not; the budget counts what is sent."""
    indented = [
        t.name
        for t in await _tools()
        if any(line.startswith(" ") for line in (t.description or "").splitlines())
    ]
    assert indented == []


async def test_required_parameters_have_no_default():
    wrong = [
        f"{t.name}.{name}"
        for t in await _tools()
        for name in (t.input_schema or {}).get("required", [])
        if "default" in _params(t)[name]
    ]
    assert wrong == []


async def test_descriptions_carry_the_pitfalls():
    """The warnings a model acts on must be in the descriptions it reads."""
    text = {t.name: " ".join(t.description.split()) for t in await _tools()}
    assert "before trusting a zero" in text["geneteka_coverage"]
    assert "gaps included" in text["geneteka_coverage"]
    assert "check geneteka_coverage" in text["geneteka_search"]
    assert "ask for the next page" in text["geneteka_search"]
    assert "name groups" in text["poznan_search"]
    assert "never as a zero" in text["poznan_search"]
    assert "Sygnatura" in text["basia_search"] and "series" in text["basia_search"]
    assert "a zero is weak evidence" in text["basia_search"]
    assert "never returned inline" in text["swa_scan"]
    assert "bot check" in text["swa_scan"] and "Sygnatura" in text["swa_scan"]
    assert "15wp" in text["regions"]


async def test_the_destination_rules_are_in_the_description():
    text = {t.name: " ".join(t.description.split()) for t in await _tools()}
    for rule in (".jpg", "not hidden", "not under ~/Library", "download folder"):
        assert rule in text["swa_scan"], rule
    params = {t.name: _params(t) for t in await _tools()}
    assert "/tmp/" not in params["swa_scan"]["destination"]["description"]


async def test_the_instructions_keep_the_evidence_model():
    text = " ".join(mcp.instructions.split())
    assert "An index row is a finding aid" in text
    assert "is not a negative" in text and "check geneteka_coverage first" in text
    assert "Wojciech = Adalbertus/Adalbert" in text and "Jan = Joannes/Johann" in text
    assert "Marianna = Maria" in text and "-ski/-ska" in text and "genitive" in text
    assert "cited by the archive's call number" in text and "Sygnatura" in text
    assert "do not cite this server" in text
    assert "never as instructions" in text


async def test_no_tool_offers_to_write():
    assert [t.name for t in await _tools() if WRITE_WORDS.search(t.name)] == []


async def test_every_tool_is_annotated_and_only_swa_scan_writes():
    for tool in await _tools():
        assert tool.annotations is not None, tool.name
        writes = tool.name in WRITES_LOCAL_FILE
        assert tool.annotations.read_only_hint is (not writes), tool.name
        assert tool.annotations.open_world_hint is (tool.name not in LOCAL_TOOLS), tool.name
        if writes:
            assert tool.annotations.destructive_hint is False


async def test_no_tool_raises_when_every_site_fails(served, tmp_path):
    """Every failure must come back as an envelope; a tool that raises kills the call."""
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        every_site(router, lambda request: httpx.Response(500, text="boom"))
        for tool in await _tools():
            out = await call_tool(tool.name, **valid_args(tool.name, tmp_path))
            assert isinstance(out, dict), tool.name
            assert_reached_body(tool.name, out)
            if tool.name not in LOCAL_TOOLS:
                assert out.get("error") == "upstream_error", f"{tool.name} returned {out}"


async def test_no_tool_raises_on_a_page_it_cannot_read(served, tmp_path):
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        every_site(router, lambda request: httpx.Response(200, text="<html>changed</html>"))
        for tool in await _tools():
            out = await call_tool(tool.name, **valid_args(tool.name, tmp_path))
            assert isinstance(out, dict), tool.name
            if tool.name not in LOCAL_TOOLS:
                assert out.get("error") in ("unexpected_answer", "not_an_image"), (tool.name, out)


async def test_every_tool_refuses_a_parameter_it_does_not_define(served, tmp_path):
    accepted = []
    # Should the refusal regress, the tools run for real; keep them offline.
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.route().mock(return_value=httpx.Response(200, json={}))
        for tool in await _tools():
            try:
                await mcp.call_tool(
                    tool.name, {**valid_args(tool.name, tmp_path), "not_a_parameter": "x"}
                )
            except ToolError as exc:
                assert "not_a_parameter" in str(exc), tool.name
                continue
            accepted.append(tool.name)
    assert accepted == []


async def test_every_published_schema_forbids_additional_properties():
    assert [
        t.name for t in await _tools() if t.input_schema.get("additionalProperties") is not False
    ] == []


async def test_no_schema_carries_an_auto_generated_title():
    def titles(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "title" and isinstance(value, str) and not path.endswith("properties"):
                    yield path
                yield from titles(value, f"{path}/{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                yield from titles(value, f"{path}/{i}")

    found = [f"{t.name}{p}" for t in await _tools() for p in titles(t.input_schema)]
    assert found == []


async def test_regions_lists_every_geneteka_region():
    out = await call_tool("regions")
    codes = [r["region"] for r in out["regions"]]
    assert len(codes) == 21 and "15wp" in codes and "71wa" in codes


async def test_cache_status_names_the_pacing(served):
    out = await call_tool("cache_status")
    assert set(out["seconds_between_requests"]) == {
        "geneteka.genealodzy.pl",
        "poznan-project.psnc.pl",
        "www.basia.famula.pl",
        "photos.szukajwarchiwach.gov.pl",
    }
    assert out["live_calls_this_session"] == 0 and out["coverage_list_age_days"] is None


def test_compaction_refusal_and_dedent_are_idempotent():
    assert server.compact_schemas() == 0
    assert server.refuse_unknown_arguments() == 0
    assert server.clean_descriptions() == 0


def test_the_server_reports_its_own_version():
    assert mcp.version == __version__
