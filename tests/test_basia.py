"""BaSIA: result boxes, unit addresses, the call-number warning, and truncation."""

from __future__ import annotations

from datetime import date

import pytest

from polish_archives_mcp import basia, server

from .conftest import basia_site, call_tool, fixture, form_of


def rows(name: str = "basia_jan_kowalski_usc_births_1880_1885.html") -> list[dict]:
    return basia.parse_results(fixture(name))["rows"]


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def test_a_civil_birth_entry_parses_with_its_unit_on_the_current_domain():
    first = next(r for r in rows() if r["basia_id"] == "904873")
    assert first["unit"] == "Żerków" and first["register"] == "Registry office"
    assert first["record"] == "birth record" and first["year"] == 1880
    assert first["book"] == "[Księga urodzeń]"
    assert first["persons"] == "Marianna, parents: Johann Kowalski [95%], Josepha Raczak"
    assert first["archive"] == "Archiwum Państwowe w Kaliszu" and first["archive_code"] == "11"
    assert first["basia_call_number"] == "772/1/19" and first["scan"] == 122
    assert first["unit_url"] == (
        "https://www.szukajwarchiwach.gov.pl/jednostka/-/jednostka/11962370#scan122"
    )
    assert first["basia_url"].startswith("https://www.basia.famula.pl/record/")


def test_every_row_carries_the_call_number_warning():
    for name in ("basia_jan_kowalski_usc_births_1880_1885.html", "basia_kowalski_truncated.html"):
        for row in rows(name):
            assert row["call_number_warning"] == basia.CALL_NUMBER_WARNING
    assert "Sygnatura" in basia.CALL_NUMBER_WARNING
    assert "series" in basia.CALL_NUMBER_WARNING


def test_indexer_notes_are_kept():
    row = next(r for r in rows() if r["basia_id"] == "4153222")
    assert row["indexer_notes"] == "31.01.1880 Ostrzeszów"


def test_a_link_on_the_retired_domain_gives_its_reference_and_no_unit_address():
    row = next(r for r in rows() if r["basia_id"] == "4153222")
    assert row["unit_url"] is None
    assert row["retired_link"].startswith("https://szukajwarchiwach.pl/11/730/0/1/25/")
    assert row["reference_in_link"] == "11/730/0/1/25"
    assert "no longer opens" in row["unit_url_note"]
    assert row["basia_call_number"] == "730/1/25" and row["scan"] == 53


def test_a_series_number_with_a_dot_is_read_whole():
    row = next(r for r in rows() if r["basia_id"] == "3762882")
    assert row["basia_call_number"] == "751/6.1/99"
    assert row["reference_in_link"] == "54/751/0/6.1/99"
    assert row["book"] == "Księga urodzeń, małżeństw i zgonów"


def test_a_parish_entry_without_a_scan_link_keeps_its_call_number():
    row = rows("basia_kowalski_truncated.html")[0]
    assert row["register"] == "par. rzymskokatolicka" and row["entry"] == "42"
    assert row["record"] == "birth/baptism record" and row["year"] == 1800
    assert row["archive"] == "Archdiocesan Archive in Poznan" and row["archive_code"] == "AAP"
    assert row["basia_call_number"] == "PM 015/7"
    assert row["unit_url"] is None and "scan" not in row
    assert row["other_people"].startswith("Tomas Kowalski [100%]")


def test_the_total_and_truncation_are_read():
    full = basia.parse_results(fixture("basia_jan_kowalski_usc_births_1880_1885.html"))
    assert full["total"] == 104 and full["truncated"]  # 104 matched, four kept in the fixture
    cut = basia.parse_results(fixture("basia_kowalski_truncated.html"))
    assert cut["total"] == 43684 and cut["truncated"]


def test_no_results_is_a_zero():
    parsed = basia.parse_results(fixture("basia_none.html"))
    assert parsed["rows"] == [] and parsed["total"] == 0 and not parsed["truncated"]


def test_a_page_with_neither_entries_nor_a_no_results_message_is_unexpected():
    with pytest.raises(basia.SiteError) as caught:
        basia.parse_results("<html><body>Przerwa</body></html>")
    assert caught.value.code == "unexpected_answer"


def test_the_form_names_each_person_and_the_filters():
    form = basia.search_form(
        people=[("Jan", "Kowalski"), ("Marianna", "Kowalska")],
        place="Kalisz",
        distance_km=20,
        year_from=1880,
        year_to=1885,
        similarity=85,
        unit="usc",
        record="birth",
        today=date(2026, 10, 11),
    )
    assert form["p_count"] == "2"
    assert (form["fname0"], form["lname0"], form["fname1"], form["lname1"]) == (
        "Jan", "Kowalski", "Marianna", "Kowalska",
    )  # fmt: skip
    assert form["sim1"] == "85" and form["type_unit"] == "usc" and form["type_record"] == "a"
    assert form["od"] == "1880" and form["do"] == "1885" and form["showplaces"] == "block"
    assert form["dateto"] == "2026-10-11"


# --------------------------------------------------------------------------- #
# basia_search
# --------------------------------------------------------------------------- #
async def test_a_search_posts_the_form_and_returns_rows(served, sites, monkeypatch):
    monkeypatch.setattr(server, "_today", lambda: date(2026, 10, 11))
    route = basia_site(sites)
    out = await call_tool(
        "basia_search", surname="Kowalski", given="Jan", year_from=1880, year_to=1885,
        unit="usc", record="birth", persons=["Marianna Kowalska"],
    )  # fmt: skip
    assert out["total"] == 104 and out["listed"] == 4 and out["returned"] == 4
    assert "finding aids" in out["note"]
    form = form_of(route.calls[0].request)
    assert form["lname0"] == "Kowalski" and form["fname1"] == "Marianna"
    assert form["type_record"] == "a" and form["od"] == "1880"
    assert route.calls[0].request.headers["Referer"] == "https://www.basia.famula.pl/en/"


async def test_a_truncated_search_says_how_to_see_the_rest(served, sites):
    basia_site(sites, results=fixture("basia_kowalski_truncated.html"))
    out = await call_tool("basia_search", surname="Kowalski")
    assert out["truncated"] and "43684" in out["truncated_note"]


async def test_a_zero_is_called_weak_evidence(served, sites):
    basia_site(sites, results=fixture("basia_none.html"))
    out = await call_tool("basia_search", surname="Qwxzyk")
    assert out["rows"] == [] and "weak evidence" in out["zero_note"]


async def test_searches_are_cached_a_day(served, sites):
    route = basia_site(sites)
    await call_tool("basia_search", surname="Kowalski", given="Jan")
    await call_tool("basia_search", surname="Kowalski", given="Jan", page=2)
    assert route.call_count == 1
    await call_tool("basia_search", surname="Kowalski", given="Józef")
    assert route.call_count == 2


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({"surname": ""}, "no_surname"),
        ({"surname": "Kowalski", "persons": ["A B"] * 5}, "too_many_persons"),
        ({"surname": "Kowalski", "similarity": 20}, "bad_similarity"),
        ({"surname": "Kowalski", "distance_km": 500}, "bad_distance"),
        ({"surname": "Kowalski", "year_from": 1400}, "bad_year"),
        ({"surname": "Kowalski", "page": 0}, "bad_page"),
    ],
)
async def test_arguments_are_checked_before_any_request(served, sites, args, error):
    route = basia_site(sites)
    out = await call_tool("basia_search", **args)
    assert out["error"] == error and route.call_count == 0
