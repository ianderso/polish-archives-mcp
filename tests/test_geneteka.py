"""Geneteka: the coverage list, the year spans, and the search rows."""

from __future__ import annotations

import httpx
import pytest

from polish_archives_mcp import geneteka

from .conftest import (
    FIXTURES,
    MARIACKI_BIRTHS,
    MARIACKI_DEATHS,
    MARIACKI_MARRIAGES,
    by_bdm,
    call_tool,
    fixture,
    geneteka_site,
)


def raw_fixture(name: str) -> str:
    """A recorded answer as the text the site sent."""
    return (FIXTURES / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def test_the_coverage_list_parses_every_register():
    registers = geneteka.parse_coverage(fixture("gt_registers_trimmed.html"))
    assert len(registers) == 11
    births = next(r for r in registers if r.rid == MARIACKI_BIRTHS)
    assert births.parish == "Kraków WNMP (Mariacki)"
    assert births.kind == "B" and births.region == "06mp"
    assert births.years == "1687-1700,1714-51,53-1866,1868-73,90-1909"


def test_a_register_with_no_years_listed_keeps_an_empty_string():
    registers = geneteka.parse_coverage(fixture("gt_registers_trimmed.html"))
    empty = next(r for r in registers if r.region == "01ds")
    assert empty.years == "" and empty.summary()["years"] == "(none listed)"


@pytest.mark.parametrize(
    ("years", "spans"),
    [
        ("1741-55,90,98,1810-1930", [(1741, 1755), (1790, 1790), (1798, 1798), (1810, 1930)]),
        ("1700-07,09-16,35-1879", [(1700, 1707), (1709, 1716), (1735, 1879)]),
        (
            "1799-1800,1810-47,49-50,52-1916",
            [(1799, 1800), (1810, 1847), (1849, 1850), (1852, 1916)],
        ),
        (
            "1871-72,75,77,95-98,1900,02-25",
            [(1871, 1872), (1875, 1875), (1877, 1877), (1895, 1898), (1900, 1900), (1902, 1925)],
        ),
        ("1890-99,02-05", [(1890, 1899), (1902, 1905)]),
        ("1811", [(1811, 1811)]),
        ("", []),
    ],
)
def test_shortened_years_are_read_as_geneteka_means_them(years, spans):
    assert geneteka.year_spans(years) == spans


def test_covers_says_whether_a_year_is_indexed():
    assert geneteka.covers("1687-1700,1714-51,53-1866", 1750)
    assert not geneteka.covers("1687-1700,1714-51,53-1866", 1752)
    assert not geneteka.covers("", 1850)


def test_a_births_row_carries_notes_custodian_scan_and_id():
    raw = raw_fixture("gt_b_krakow_mariacki_kowalski_p1.json")
    parsed = geneteka.parse_search(raw, "B")
    assert parsed["total"] == 60
    assert parsed["searched"] == [
        {"rid": MARIACKI_BIRTHS, "parish": "Kraków WNMP (Mariacki)", "region": "06mp"}
    ]
    first = parsed["rows"][0]
    assert first["year"] == 1856 and first["act"] == "16"
    assert first["given"] == "Jan Paweł" and first["surname"] == "Kowalski"
    assert first["mother_given"] == "Maria" and first["place"] == "Kraków"
    assert first["custodian"] == "Archiwum Narodowe w Krakowie"
    assert first["custodian_address"] == "30-960 Kraków, ul. Sienna 16"
    assert first["scan_links"] == [
        "https://www.szukajwarchiwach.gov.pl/jednostka/-/jednostka/14604751"
    ]
    assert first["geneteka_id"] == "9340839"
    assert "father" not in first  # empty cells are left out
    second = parsed["rows"][1]
    assert second["notes"] == ["Data urodzenia: 15.04.1850 r."]


def test_a_note_inside_a_name_cell_is_kept_and_attributed():
    raw = raw_fixture("gt_b_krakow_mariacki_kowalski_p1.json")
    row = geneteka.parse_search(raw, "B")["rows"][3]
    assert row["surname"] == "Jakubowski"
    assert "surname: Inne nazwiska: Kowalski" in row["notes"]
    assert any(n.startswith("Uwagi: uznanie dziecka") for n in row["notes"])


def test_a_marriage_row_uses_the_marriage_columns():
    raw = raw_fixture("gt_m_krakow_mariacki_kowalski.json")
    rows = geneteka.parse_search(raw, "S")["rows"]
    assert rows[1]["groom_surname"] == "Kowalski"
    assert rows[1]["groom_parents"] == "Andrzej, Marianna Bila"
    assert rows[1]["bride_surname"] == "Kos"
    assert "bride_surname: Inne nazwiska: Kosińska" in rows[1]["notes"]
    assert "Data ślubu: 04.11.1860 r." in rows[1]["notes"]
    assert "scan_links" not in rows[1]


def test_an_answer_that_is_not_json_is_unexpected():
    with pytest.raises(geneteka.SiteError) as caught:
        geneteka.parse_search("<html>maintenance</html>", "B")
    assert caught.value.code == "unexpected_answer"


def test_a_row_of_the_wrong_width_is_unexpected():
    with pytest.raises(geneteka.SiteError) as caught:
        geneteka.parse_search('{"recordsTotal": 1, "data": [[1850, "1", "x"]]}', "B")
    assert caught.value.code == "unexpected_answer"


# --------------------------------------------------------------------------- #
# geneteka_coverage
# --------------------------------------------------------------------------- #
async def test_coverage_lists_a_parishs_registers_with_rid_and_years(served, sites):
    geneteka_site(sites)
    out = await call_tool("geneteka_coverage", place="mariacki")
    assert out["matches"] == 3
    assert [r["record_type"] for r in out["registers"]] == ["B", "M", "D"]
    births = out["registers"][0]
    assert births["rid"] == MARIACKI_BIRTHS and births["records"] == "births"
    assert births["region_name"] == "małopolskie"
    assert "rid=8959" in births["search_url"]


async def test_coverage_matches_without_diacritics_and_by_region(served, sites):
    geneteka_site(sites)
    out = await call_tool("geneteka_coverage", place="krakow", region="06mp")
    assert out["matches"] == 7
    assert {r["region"] for r in out["registers"]} == {"06mp"}


async def test_coverage_marks_whether_a_year_is_indexed(served, sites):
    geneteka_site(sites)
    out = await call_tool("geneteka_coverage", place="Mariacki", year=1752)
    by_type = {r["record_type"]: r["covers_year"] for r in out["registers"]}
    assert by_type == {"B": False, "M": True, "D": False}


async def test_the_coverage_list_is_cached_for_a_week(served, sites):
    route = geneteka_site(sites)
    await call_tool("geneteka_coverage", place="Mariacki")
    await call_tool("geneteka_coverage", place="Warszawa")
    assert route.call_count == 1
    await call_tool("geneteka_coverage", place="Warszawa", refresh=True)
    assert route.call_count == 2


async def test_an_unindexed_place_says_what_a_miss_means(served, sites):
    geneteka_site(sites)
    out = await call_tool("geneteka_coverage", place="Nowhereville")
    assert out["matches"] == 0 and "not indexed in Geneteka" in out["note"]


async def test_an_empty_coverage_page_is_an_error_and_not_cached(served, sites):
    route = geneteka_site(sites, coverage="<html><body>Przerwa techniczna</body></html>")
    out = await call_tool("geneteka_coverage", place="Kraków")
    assert out["error"] == "unexpected_answer"
    await call_tool("geneteka_coverage", place="Kraków")
    assert route.call_count == 2


# --------------------------------------------------------------------------- #
# geneteka_search
# --------------------------------------------------------------------------- #
async def test_search_by_rid_reads_the_register_and_its_region(served, sites):
    route = geneteka_site(sites, search=by_bdm)
    out = await call_tool(
        "geneteka_search", record_type="B", surname="Kowalski", rid=MARIACKI_BIRTHS,
        year_from=1850, year_to=1870,
    )  # fmt: skip
    assert out["region"] == "06mp" and out["register"]["parish"] == "Kraków WNMP (Mariacki)"
    assert out["total"] == 60 and out["pages"] == 2 and out["next_page"] == 2
    assert out["returned"] == 5 and out["rows"][0]["surname"] == "Kowalski"
    assert "finding aids" in out["note"]
    search = [c.request for c in route.calls if c.request.url.path == "/api/getAct.php"][0]
    params = search.url.params
    assert params["bdm"] == "B" and params["w"] == "06mp" and params["rid"] == str(MARIACKI_BIRTHS)
    assert params["from_date"] == "1850" and params["to_date"] == "1870"
    assert params["start"] == "0" and params["length"] == "50"
    assert search.headers["X-Requested-With"] == "XMLHttpRequest"
    assert search.headers["Referer"].startswith("https://geneteka.genealodzy.pl/index.php?")


async def test_marriages_are_asked_for_as_geneteka_s(served, sites):
    route = geneteka_site(sites, search=by_bdm)
    out = await call_tool(
        "geneteka_search", record_type="M", surname="Kowalski", rid=MARIACKI_MARRIAGES
    )
    assert out["records"] == "marriages" and out["rows"][1]["groom_surname"] == "Kowalski"
    assert route.calls[-1].request.url.params["bdm"] == "S"


async def test_exact_is_sent_as_exac(served, sites):
    route = geneteka_site(sites, search=by_bdm)
    await call_tool(
        "geneteka_search", record_type="D", surname="Kowalski", rid=MARIACKI_DEATHS, exact=True
    )
    assert route.calls[-1].request.url.params["exac"] == "1"


async def test_the_second_page_starts_at_row_fifty(served, sites):
    route = geneteka_site(sites, search=by_bdm)
    await call_tool("geneteka_search", record_type="B", surname="Kowalski", region="06mp", page=2)
    assert route.calls[-1].request.url.params["start"] == "50"


async def test_a_region_wide_search_says_every_register_was_searched(served, sites):
    geneteka_site(sites, search=by_bdm)
    out = await call_tool(
        "geneteka_search", record_type="B", surname="Kowalski", given="Kajetan", region="06mp"
    )
    assert out["searched"] == "every register in małopolskie" and out["total"] == 1
    assert "register" not in out


async def test_a_zero_says_it_covers_only_what_was_indexed(served, sites):
    geneteka_site(sites, search=by_bdm)
    out = await call_tool("geneteka_search", record_type="B", surname="Qwxzyk", rid=MARIACKI_BIRTHS)
    assert out["total"] == 0 and out["rows"] == []
    assert "not a negative" in out["zero_note"] and "geneteka_coverage" in out["zero_note"]
    assert out["searched"][0]["rid"] == MARIACKI_BIRTHS


async def test_years_outside_a_registers_coverage_are_named(served, sites):
    geneteka_site(sites, search=by_bdm)
    out = await call_tool(
        "geneteka_search", record_type="B", surname="Kowalski", rid=MARIACKI_BIRTHS,
        year_from=1700, year_to=1716,
    )  # fmt: skip
    assert out["years_not_indexed"] == "1701-1713"


async def test_a_rid_of_another_record_type_is_refused_naming_the_right_one(served, sites):
    route = geneteka_site(sites, search=by_bdm)
    out = await call_tool(
        "geneteka_search", record_type="M", surname="Kowalski", rid=MARIACKI_BIRTHS
    )
    assert out["error"] == "wrong_register_type"
    assert f"rid {MARIACKI_MARRIAGES}" in out["message"]
    assert all(c.request.url.path != "/api/getAct.php" for c in route.calls)


async def test_an_unknown_rid_is_refused(served, sites):
    geneteka_site(sites, search=by_bdm)
    out = await call_tool("geneteka_search", record_type="B", surname="Kowalski", rid=1)
    assert out["error"] == "unknown_rid"


async def test_a_rid_in_another_region_is_refused(served, sites):
    geneteka_site(sites, search=by_bdm)
    out = await call_tool(
        "geneteka_search", record_type="B", surname="Kowalski", rid=MARIACKI_BIRTHS,
        region="15wp",
    )  # fmt: skip
    assert out["error"] == "region_mismatch"


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({"surname": "Kowalski"}, "no_region"),
        ({"surname": " ", "region": "06mp"}, "no_surname"),
        ({"surname": "Kowalski", "region": "99xx"}, "unknown_region"),
        ({"surname": "Kowalski", "region": "06mp", "year_from": 1900, "year_to": 1850}, "bad_year"),
        ({"surname": "Kowalski", "region": "06mp", "page": 0}, "bad_page"),
    ],
)
async def test_search_arguments_are_checked_before_any_request(served, sites, args, error):
    route = geneteka_site(sites, search=by_bdm)
    out = await call_tool("geneteka_search", record_type="B", **args)
    assert out["error"] == error and route.call_count == 0


async def test_an_outage_is_not_a_zero(served, sites):
    geneteka_site(sites, search=httpx.Response(503, text="busy"))
    out = await call_tool("geneteka_search", record_type="B", surname="Kowalski", region="06mp")
    assert out["error"] == "upstream_error" and "not an empty result" in out["message"]


async def test_an_unreadable_answer_is_not_cached(served, sites):
    route = geneteka_site(sites, search="<html>Przerwa techniczna</html>")
    for _ in range(2):
        out = await call_tool("geneteka_search", record_type="B", surname="Kowalski", region="06mp")
        assert out["error"] == "unexpected_answer"
    assert route.call_count == 2
