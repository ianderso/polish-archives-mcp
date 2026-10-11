"""The Poznań Project: name groups, result blocks, custodians and the 'too many' answer."""

from __future__ import annotations

import httpx
import pytest

from polish_archives_mcp import poznan

from .conftest import call_tool, fixture, form_of, poznan_site


def groups(role: str = "groom") -> list[tuple[str, str]]:
    return poznan.name_groups(fixture("pp_form_name_groups.html"), f"{role}_firstname")


# --------------------------------------------------------------------------- #
# Name groups
# --------------------------------------------------------------------------- #
def test_the_form_gives_the_name_groups_without_any():
    found = groups()
    assert ("25", "Joannes / Jan / Johann") in found
    assert all(value != "0" for value, _ in found)


@pytest.mark.parametrize(
    ("given", "value"),
    [
        ("Jan", "25"),
        ("Johann", "25"),
        ("JOANNES", "25"),
        ("Johannes", "25"),  # begins with a group's spelling
        ("Wojciech", "1"),
        ("Adalbert", "1"),  # the group's spelling without its optional ending
        ("Adalbertus", "1"),  # and with it
        ("Wawrzyniec", "28"),  # begins with Wawrzyn
        ("Józef", "26"),
        ("Jozef", "26"),
        ("Mikołaj", "34"),  # the group writes Mikolaj
    ],
)
def test_a_given_name_finds_its_group(given, value):
    assert poznan.pick_group(groups(), given) == value


@pytest.mark.parametrize(
    ("given", "value"),
    [("Marianna", "29"), ("Maria", "29"), ("Apolonia", "5"), ("Apollonia", "5"), ("Jadwiga", "19")],
)
def test_a_brides_given_name_finds_its_group(given, value):
    assert poznan.pick_group(groups("bride"), given) == value


def test_a_name_in_no_group_finds_none():
    assert poznan.pick_group(groups(), "Zbigniew") is None


def test_a_name_that_begins_several_groups_is_ambiguous():
    with pytest.raises(poznan.AmbiguousName) as caught:
        poznan.pick_group(groups(), "Chris")  # Christian, and Christoph(orus)
    assert caught.value.labels == ["Christian / Krystian", "Christoph(orus) / Krzysztof"]


# --------------------------------------------------------------------------- #
# Result blocks
# --------------------------------------------------------------------------- #
def test_the_results_parse_into_rows():
    parsed = poznan.parse_results(fixture("pp_kowalski_jan_1850_1855.html"))
    assert parsed["exact"] == 37 and parsed["above_threshold"] == 46
    assert not parsed["too_many"] and len(parsed["rows"]) == 5
    first = parsed["rows"][0]
    assert first["poznan_id"] == "131519"
    assert first["register"] == "Catholic parish" and first["parish"] == "Bądkowo"
    assert first["entry"] == "5" and first["year"] == 1850
    assert first["match"] == "exact" and first["groom_similarity"] == 100
    assert first["groom"] == "Jan Kowalski (28 lat); ojciec: Łukasz +, matka: Apolonia Wyżykowska"
    assert first["bride"].startswith("Marianna Sobczak (16 lat)")
    assert first["archive_page"] == 18


def test_a_widowers_block_is_read_too():
    rows = poznan.parse_results(fixture("pp_kowalski_jan_1850_1855.html"))["rows"]
    widowed = next(r for r in rows if r["parish"] == "Domachowo")
    assert "wdowiec" in widowed["groom"] and "z domu" in widowed["bride"]


def test_a_comment_keeps_its_words_and_date_but_not_who_wrote_it():
    rows = poznan.parse_results(fixture("pp_kowalski_jan_1850_1855.html"))["rows"]
    commented = next(r for r in rows if "comments" in r)
    assert commented["comments"] == [{"text": "w moim drzewie", "date": "25-07-2018"}]
    assert "example.org" not in str(commented) and "Researcher" not in str(commented)


def test_an_approximate_match_is_marked():
    rows = poznan.parse_results(fixture("pp_kowalski_jan_1850_1855.html"))["rows"]
    rough = next(r for r in rows if r["parish"] == "Sieradz")
    assert rough["match"] == "approximate" and rough["groom_similarity"] == 81


def test_too_many_is_its_own_answer():
    parsed = poznan.parse_results(fixture("pp_kowalski_too_many.html"))
    assert parsed["too_many"] and parsed["rows"] == []
    assert parsed["exact"] == 323 and parsed["above_threshold"] == 452


def test_nothing_found_is_a_zero():
    parsed = poznan.parse_results(fixture("pp_none.html"))
    assert parsed["rows"] == [] and not parsed["too_many"] and parsed["exact"] == 0


def test_a_page_with_neither_is_unexpected():
    with pytest.raises(poznan.SiteError) as caught:
        poznan.parse_results("<div>Serwis w przebudowie</div>")
    assert caught.value.code == "unexpected_answer"


def test_an_archive_page_names_who_holds_the_original():
    assert poznan.parse_archive_page(fixture("pp_arch18.htm")) == (
        "State Archive in Włocławek, Poland"
    )


# --------------------------------------------------------------------------- #
# poznan_search
# --------------------------------------------------------------------------- #
async def test_a_search_posts_the_form_and_adds_custodians(served, sites):
    route = poznan_site(sites)
    out = await call_tool(
        "poznan_search", groom_surname="Kowalski", groom_given="Jan", year_from=1850, year_to=1855
    )
    assert out["exact_matches"] == 37 and out["total"] == 5 and out["returned"] == 5
    assert out["groom_name_group"] == "Joannes / Jan / Johann"
    first = out["rows"][0]
    assert first["custodian"] == "State Archive in Włocławek, Poland"
    assert first["record_location_url"].endswith("/pages/arch_location/arch18.htm")
    assert "archive_page" not in first
    posted = [c.request for c in route.calls if c.request.url.path == "/getresults.php"][0]
    form = form_of(posted)
    assert form["groom_lastname"] == "Kowalski" and form["groom_firstname"] == "25"
    assert form["extended_window_lastname_mode"] == "both" and form["lastname"] == ""
    assert form["year_from"] == "1850" and form["threshold"] == "80"
    assert form["confession"] == "0"
    assert posted.headers["X-Requested-With"] == "XMLHttpRequest"


async def test_any_surname_uses_the_sites_any_mode(served, sites):
    route = poznan_site(sites)
    await call_tool("poznan_search", any_surname="Kowalski", confession="protestant")
    form = form_of(route.calls[-1].request)
    assert form["extended_window_lastname_mode"] == "any" and form["lastname"] == "Kowalski"
    assert form["confession"] == "2"


async def test_without_a_given_name_the_form_is_not_fetched(served, sites):
    route = poznan_site(sites)
    await call_tool("poznan_search", groom_surname="Kowalski")
    assert [c.request.url.path for c in route.calls] == ["/getresults.php"]


async def test_the_name_groups_are_cached(served, sites):
    route = poznan_site(sites)
    await call_tool("poznan_search", groom_surname="Kowalski", groom_given="Jan")
    await call_tool("poznan_search", groom_surname="Kowalski", groom_given="Wojciech")
    assert sum(1 for c in route.calls if c.request.url.path == "/") == 1


async def test_an_ambiguous_given_name_returns_the_candidates(served, sites):
    poznan_site(sites)
    out = await call_tool("poznan_search", groom_surname="Kowalski", groom_given="Chris")
    assert out["error"] == "ambiguous_given_name" and len(out["candidates"]) == 2


async def test_an_unknown_given_name_returns_the_groups(served, sites):
    route = poznan_site(sites)
    out = await call_tool("poznan_search", groom_surname="Kowalski", groom_given="Zbigniew")
    assert out["error"] == "unknown_given_name" and out["role"] == "groom"
    assert "Joannes / Jan / Johann" in out["groups"]
    assert all(c.request.url.path != "/getresults.php" for c in route.calls)


async def test_too_many_results_is_never_a_zero(served, sites):
    poznan_site(sites, results=fixture("pp_kowalski_too_many.html"))
    out = await call_tool("poznan_search", groom_surname="Kowalski")
    assert out["error"] == "too_many_results" and "not a zero" in out["message"]
    assert out["exact_matches"] == 323 and out["above_threshold"] == 452


async def test_a_zero_says_what_the_project_covers(served, sites):
    poznan_site(sites, results=fixture("pp_none.html"))
    out = await call_tool("poznan_search", groom_surname="Qwxzyk")
    assert out["rows"] == [] and "1800-1899" in out["zero_note"]


async def test_an_archive_not_in_the_table_is_read_from_its_page_and_cached(
    served, sites, monkeypatch
):
    monkeypatch.setattr(poznan, "ARCHIVES", {})
    route = poznan_site(sites)
    out = await call_tool("poznan_search", groom_surname="Kowalski", groom_given="Jan")
    assert out["rows"][0]["custodian"] == "State Archive in Włocławek, Poland"
    pages = [c.request.url.path for c in route.calls if "arch_location" in c.request.url.path]
    assert len(pages) == 3  # at most three archive pages a call
    assert all("custodian" in r for r in out["rows"][:3])
    await call_tool("poznan_search", groom_surname="Kowalski", groom_given="Jan")
    again = [c.request.url.path for c in route.calls if "arch_location" in c.request.url.path]
    assert len(again) == 3 + 2  # the three already read come from the cache


async def test_an_archive_page_that_fails_leaves_only_its_address(served, sites, monkeypatch):
    monkeypatch.setattr(poznan, "ARCHIVES", {})
    poznan_site(sites, archive=httpx.Response(404, text="Not Found"))
    out = await call_tool("poznan_search", groom_surname="Kowalski")
    assert "custodian" not in out["rows"][0] and out["rows"][0]["record_location_url"]


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({}, "no_surname"),
        ({"groom_surname": "Kowalski", "any_surname": "Kowalski"}, "conflicting_criteria"),
        ({"groom_surname": "Kowalski", "year_from": 1790}, "bad_year"),
        ({"groom_surname": "Kowalski", "year_to": 1905}, "bad_year"),
        ({"groom_surname": "Kowalski", "threshold": 30}, "bad_threshold"),
        ({"groom_surname": "Kowalski", "page": 0}, "bad_page"),
    ],
)
async def test_arguments_are_checked_before_any_request(served, sites, args, error):
    route = poznan_site(sites)
    out = await call_tool("poznan_search", **args)
    assert out["error"] == error and route.call_count == 0


async def test_rows_page_fifty_at_a_time(served, sites, monkeypatch):
    many = poznan.parse_results(fixture("pp_kowalski_jan_1850_1855.html"))
    many["rows"] = many["rows"] * 12  # 60 rows
    monkeypatch.setattr(poznan, "parse_results", lambda page, url="": many)
    poznan_site(sites)
    first = await call_tool("poznan_search", groom_surname="Kowalski")
    second = await call_tool("poznan_search", groom_surname="Kowalski", page=2)
    assert (first["returned"], first["next_page"]) == (50, 2)
    assert (second["returned"], second["next_page"]) == (10, None)
