"""Ask the live sites what the recorded fixtures cannot. Run by hand.

    uv run python -m tests.live_check

Each check calls a tool against the real site, through the real client at
its real pace (one request at a time per site, four seconds apart, ten for
BaSIA), so the whole run takes a minute or two. It checks that each site
still answers with the shape the server reads:

* Geneteka's coverage list still lists Kraków's St Mary's (Mariacki)
  registers, and its search still returns Kowalski there with the custodian,
  a zero still names the register searched, and a register of the wrong type
  is still refused before any search;
* the Poznań Project still matches Jan to its name group, still says who
  holds each register, still answers "too many" for a broad search, and still
  offers its name groups when a name fits none;
* BaSIA still returns the Żerków civil birth entry with its unit on the
  current domain and the call-number warning, and still says when nothing
  matches;
* the photo host still serves a full-size scan by name (a microfilm target
  card, scan 1 of AP Kalisz 11/772/0/1/19, whose name was read from the unit
  page in a browser on 2026-10-11), and still serves its "file unavailable"
  picture, refused, for a name it does not hold.

It is not a test module: pytest does not collect it, and CI never runs it,
because the suite must never depend on someone else's server being up. The
scan is written to a temporary directory, set as the download folder, and
deleted.

Exit status 0 if every check passed, 1 if any failed.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from polish_archives_mcp import server
from polish_archives_mcp.client import ArchivesHttp
from polish_archives_mcp.config import load_config

#: A scan the photo host holds: scan 1 (a microfilm target card) of AP Kalisz
#: 11/772/0/1/19, read from its unit page in a browser on 2026-10-11.
TARGET_CARD = "a482f4b3da55f84956a578374fcd8f1398591b55345b7d9adcbc3e5416bf401e"

#: (tool, arguments, check, what the check means). ``{tmp}`` in an argument
#: is replaced by the temporary directory.
CHECKS: list[tuple[str, dict, Callable[[dict], bool], str]] = [
    (
        "geneteka_coverage",
        {"place": "Mariacki", "region": "06mp", "year": 1860},
        lambda r: any(
            g["rid"] == 8959 and g["years"].startswith("1687") and g["covers_year"]
            for g in r["registers"]
        ),
        "the coverage list names Kraków Mariacki's births register, rid 8959, from 1687",
    ),
    (
        "geneteka_search",
        {
            "record_type": "B",
            "surname": "Kowalski",
            "rid": 8959,
            "year_from": 1850,
            "year_to": 1870,
        },
        lambda r: (
            r["total"] >= 50
            and r["rows"][0].get("custodian") == "Archiwum Narodowe w Krakowie"
            and r["next_page"] == 2
        ),
        "Kowalski births at Mariacki 1850-1870: two pages, the custodian on each row",
    ),
    (
        "geneteka_search",
        {
            "record_type": "M",
            "surname": "Kowalski",
            "rid": 1301,
            "year_from": 1850,
            "year_to": 1860,
        },
        lambda r: r["total"] >= 20 and any(row.get("groom_surname") for row in r["rows"]),
        "Kowalski marriages at Mariacki 1850-1860 read with the marriage columns",
    ),
    (
        "geneteka_search",
        {"record_type": "B", "surname": "Qwxzyk", "rid": 8959},
        lambda r: r["total"] == 0 and r["searched"][0]["rid"] == 8959,
        "a zero still names the register searched",
    ),
    (
        "geneteka_search",
        {"record_type": "M", "surname": "Kowalski", "rid": 8959},
        lambda r: r["error"] == "wrong_register_type" and "rid 1301" in r["message"],
        "a births rid asked for marriages is refused, naming the marriages rid",
    ),
    (
        "poznan_search",
        {"groom_surname": "Kowalski", "groom_given": "Jan", "year_from": 1850, "year_to": 1855},
        lambda r: (
            r["exact_matches"] >= 30
            and r["groom_name_group"] == "Joannes / Jan / Johann"
            and all(row.get("custodian") for row in r["rows"][:10])
        ),
        "Jan Kowalski as groom 1850-1855: the name group, and who holds each register",
    ),
    (
        "poznan_search",
        {"groom_surname": "Kowalski", "year_from": 1850, "year_to": 1855},
        lambda r: r["error"] == "too_many_results" and r["above_threshold"] > 300,
        "Kowalski as groom with any given name is 'too many', never a zero",
    ),
    (
        "poznan_search",
        {"groom_surname": "Kowalski", "groom_given": "Zbigniew"},
        lambda r: r["error"] == "unknown_given_name" and len(r["groups"]) >= 40,
        "a given name in no group returns the groups",
    ),
    (
        "basia_search",
        {
            "surname": "Kowalski",
            "given": "Jan",
            "year_from": 1880,
            "year_to": 1885,
            "unit": "usc",
            "record": "birth",
        },
        lambda r: (
            r["total"] >= 100
            and any(
                row["basia_id"] == "904873"
                and row["unit_url"].endswith("/jednostka/11962370#scan122")
                and row["basia_call_number"] == "772/1/19"
                and row["call_number_warning"]
                for row in r["rows"]
            )
        ),
        "BaSIA's Żerków 1880 entry: call number, scan, unit on the current domain",
    ),
    (
        "basia_search",
        {"surname": "Qwxzyk"},
        lambda r: r["total"] == 0 and r["rows"] == [] and "zero_note" in r,
        "BaSIA's 'no search results' is read as a zero",
    ),
    (
        "swa_scan",
        {"hash": TARGET_CARD, "destination": "{tmp}/target-card.jpg"},
        lambda r: r["width"] == 3500 and r["bytes"] > 100_000,
        "the photo host serves a full-size scan by name",
    ),
    (
        "swa_scan",
        {"hash": "0" * 64, "destination": "{tmp}/nothing.jpg"},
        lambda r: r["error"] == "scan_unavailable",
        "a name the host does not hold gets its 'file unavailable' picture, refused",
    ),
]

#: Checks whose expected answer is a refusal.
REFUSALS = {
    "a births rid asked for marriages is refused, naming the marriages rid",
    "Kowalski as groom with any given name is 'too many', never a zero",
    "a given name in no group returns the groups",
    "a name the host does not hold gets its 'file unavailable' picture, refused",
}


async def main() -> int:
    cfg = load_config()
    failed = 0
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as cache, tempfile.TemporaryDirectory() as tmp:
        http = ArchivesHttp(
            Path(cache), timeout=cfg.timeout, min_interval=cfg.min_interval, contact=cfg.contact
        )
        server.runtime.config = dataclasses.replace(cfg, download_dir=Path(tmp))
        server.runtime.http = http
        server.runtime.coverage = None
        for tool, args, check, meaning in CHECKS:
            args = {
                k: v.replace("{tmp}", tmp) if isinstance(v, str) else v for k, v in args.items()
            }
            result = json.loads((await server.mcp.call_tool(tool, args)).content[0].text)
            try:
                ok = ("error" not in result or meaning in REFUSALS) and bool(check(result))
            except (KeyError, IndexError, TypeError, AttributeError):
                ok = False
            failed += not ok
            print(f"{'PASS' if ok else 'FAIL'}  {tool}: {meaning}")
            if not ok:
                print(f"      got: {json.dumps(result, ensure_ascii=False)[:600]}")
        status = json.loads((await server.mcp.call_tool("cache_status", {})).content[0].text)
        print(f"\nrequests by host: {status['calls_by_host']}")
        await http.aclose()
    total = len(CHECKS)
    print(f"{total - failed}/{total} passed in {time.monotonic() - started:.0f} s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
