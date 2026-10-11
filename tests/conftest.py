"""Shared fixtures. Every test runs against mocked sites; nothing touches the network.

The fixtures under ``fixtures/`` are real responses recorded on 2026-10-11
(see docs/API-NOTES.md), trimmed to a few entries each. The examples are
deliberately ordinary: the surname Kowalski, searched in Kraków's St Mary's
(Mariacki) parish, and the same surname in the Poznań Project and BaSIA. One
user comment's author and e-mail address in a Poznań Project answer were
replaced with placeholders, and the Poznań Project's name-group list was cut
to fewer options.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from polish_archives_mcp import server
from polish_archives_mcp.client import BASIA, GENETEKA, PHOTOS, POZNAN, ArchivesHttp
from polish_archives_mcp.config import Config

FIXTURES = Path(__file__).parent / "fixtures"

#: Registers in the trimmed coverage list.
MARIACKI_BIRTHS, MARIACKI_MARRIAGES, MARIACKI_DEATHS = 8959, 1301, 8960

#: A real scan's name and a stand-in for its bytes: a JPEG frame header that
#: says 3500 x 2393, the size of a full scan.
SCAN_HASH = "ab" * 32


def fixture(name: str) -> Any:
    """Load one recorded response: JSON for .json files, bytes for .jpg, text otherwise."""
    path = FIXTURES / name
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix == ".jpg":
        return path.read_bytes()
    return path.read_text(encoding="utf-8")


def jpeg(width: int = 3500, height: int = 2393, pad: int = 2000) -> bytes:
    """A minimal JPEG: start of image, a JFIF segment, a frame header, padding, end."""
    app0 = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof = (
        b"\xff\xc0\x00\x11\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    )
    return b"\xff\xd8" + app0 + sof + b"\x00" * pad + b"\xff\xd9"


def make_http(tmp_path: Path, **kwargs) -> ArchivesHttp:
    """A client with no pacing and no back-off, caching under ``tmp_path``."""
    options: dict[str, Any] = {"min_interval": 0.0, "backoff": 0.0, "host_floors": {}}
    options.update(kwargs)
    return ArchivesHttp(tmp_path / "cache", **options)


@pytest.fixture
def http(tmp_path) -> ArchivesHttp:
    return make_http(tmp_path)


@pytest.fixture
def served(tmp_path, monkeypatch) -> ArchivesHttp:
    """Install a fast test client as the server's client for the duration of a test."""
    c = make_http(tmp_path)
    monkeypatch.setattr(server.runtime, "http", c)
    monkeypatch.setattr(server.runtime, "config", Config(cache_dir=tmp_path / "cache"))
    monkeypatch.setattr(server.runtime, "coverage", None)
    return c


@pytest.fixture
def sites():
    """A respx router. Any request it does not expect fails the test."""
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        yield router


Answer = Any  # str | bytes | dict | httpx.Response | Callable[[httpx.Request], ...]


def _respond(answer: Answer, request: httpx.Request) -> httpx.Response:
    if callable(answer):
        answer = answer(request)
    if isinstance(answer, httpx.Response):
        return answer
    if isinstance(answer, bytes):
        return httpx.Response(200, content=answer, headers={"content-type": "image/jpeg"})
    if isinstance(answer, dict | list):
        return httpx.Response(
            200, text=json.dumps(answer), headers={"content-type": "text/html; charset=UTF-8"}
        )
    return httpx.Response(200, text=answer, headers={"content-type": "text/html; charset=UTF-8"})


def geneteka_site(
    router: respx.MockRouter, search: Answer | None = None, coverage: Answer | None = None
) -> respx.Route:
    """Geneteka: the coverage list at rejestry.php, searches at api/getAct.php."""

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rejestry.php":
            return _respond(
                coverage if coverage is not None else fixture("gt_registers_trimmed.html"),
                request,
            )
        if request.url.path == "/api/getAct.php" and search is not None:
            return _respond(search, request)
        return httpx.Response(599, text=f"unmocked {request.url}")

    return router.route(host=GENETEKA).mock(side_effect=respond)


def by_bdm(request: httpx.Request) -> Any:
    """Answer a Geneteka search from the fixture for its record type."""
    params = request.url.params
    if params.get("search_lastname") == "Qwxzyk":
        return fixture("gt_b_krakow_mariacki_none.json")
    if params.get("rid") == "B":
        return fixture("gt_b_malopolskie_kowalski_kajetan.json")
    return fixture(
        {
            "B": "gt_b_krakow_mariacki_kowalski_p1.json",
            "S": "gt_m_krakow_mariacki_kowalski.json",
            "D": "gt_d_krakow_mariacki_kowalski_exact.json",
        }[params["bdm"]]
    )


def poznan_site(
    router: respx.MockRouter,
    results: Answer | None = None,
    archive: Answer | None = None,
) -> respx.Route:
    """The Poznań Project: the form at /, results at getresults.php, archive pages."""

    def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/" and request.method == "GET":
            return _respond(fixture("pp_form_name_groups.html"), request)
        if path == "/getresults.php" and request.method == "POST":
            return _respond(
                results if results is not None else fixture("pp_kowalski_jan_1850_1855.html"),
                request,
            )
        if path.startswith("/pages/arch_location/"):
            return _respond(archive if archive is not None else fixture("pp_arch18.htm"), request)
        return httpx.Response(599, text=f"unmocked {request.url}")

    return router.route(host=POZNAN).mock(side_effect=respond)


def basia_site(router: respx.MockRouter, results: Answer | None = None) -> respx.Route:
    """BaSIA: the extended search posted to /en/."""

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/en/" and request.method == "POST":
            return _respond(
                results
                if results is not None
                else fixture("basia_jan_kowalski_usc_births_1880_1885.html"),
                request,
            )
        return httpx.Response(599, text=f"unmocked {request.url}")

    return router.route(host=BASIA).mock(side_effect=respond)


def photos_site(router: respx.MockRouter, answer: Answer | None = None) -> respx.Route:
    """The photo host: /<hash>_max."""
    return router.route(host=PHOTOS).mock(
        side_effect=lambda request: _respond(answer if answer is not None else jpeg(), request)
    )


def every_site(router: respx.MockRouter, respond: Callable[[httpx.Request], Any]) -> None:
    """Route all four hosts to one handler."""
    for host in (GENETEKA, POZNAN, BASIA, PHOTOS):
        router.route(host=host).mock(side_effect=respond)


async def call_tool(tool_name: str, /, **arguments) -> dict:
    """Invoke a tool the way a client does, so Field defaults are resolved."""
    result = await server.mcp.call_tool(tool_name, arguments)
    return json.loads(result.content[0].text)


def form_of(request: httpx.Request) -> dict[str, str]:
    """A posted form body as a dict."""
    return dict(httpx.QueryParams(request.content.decode()))


# --------------------------------------------------------------------------- #
# Argument building for whole-surface sweeps
# --------------------------------------------------------------------------- #
#: Errors a tool returns from its own input checks, before any work. A sweep
#: that gets one of these has not tested what it thinks it has.
LOCAL_VALIDATION_ERRORS = frozenset(
    {
        "no_place",
        "no_surname",
        "no_region",
        "unknown_region",
        "bad_year",
        "bad_page",
        "bad_threshold",
        "bad_similarity",
        "bad_distance",
        "conflicting_criteria",
        "too_many_persons",
        "invalid_hash",
        "no_such_directory",
        "destination_exists",
        "relative_destination",
        "bad_extension",
        "hidden_path",
        "protected_location",
        "outside_download_dir",
    }
)

#: Arguments that carry each tool past its own checks. swa_scan's
#: destination is filled in per test, under tmp_path.
VALID_ARGS: dict[str, dict] = {
    "regions": {},
    "geneteka_coverage": {"place": "Kraków"},
    "geneteka_search": {"record_type": "B", "surname": "Kowalski", "region": "06mp"},
    "poznan_search": {"groom_surname": "Kowalski", "year_from": 1850, "year_to": 1855},
    "basia_search": {"surname": "Kowalski", "given": "Jan"},
    "swa_scan": {"hash": SCAN_HASH},
    "cache_status": {},
}


def valid_args(tool_name: str, tmp_path: Path) -> dict:
    """VALID_ARGS for one tool, with a fresh destination for swa_scan."""
    args = dict(VALID_ARGS[tool_name])
    if tool_name == "swa_scan":
        args["destination"] = str(tmp_path / f"sweep-{len(list(tmp_path.iterdir()))}.jpg")
    return args


def assert_reached_body(tool_name: str, result) -> None:
    """Fail if a sweep stopped at input validation instead of the tool's body."""
    if isinstance(result, dict) and result.get("error") in LOCAL_VALIDATION_ERRORS:
        raise AssertionError(
            f"{tool_name} rejected the sweep's arguments with {result['error']!r}; "
            f"update VALID_ARGS in tests/conftest.py. Message: {result.get('message')!r}"
        )
