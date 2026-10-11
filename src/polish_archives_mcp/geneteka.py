"""Geneteka: the Polskie Towarzystwo Genealogiczne's index of parish and civil registers.

Two things are read, both over plain HTTP:

* the coverage list (``rejestry.php``): every register indexed, by region,
  parish and record type, with the years done exactly as Geneteka writes
  them (``1741-55,90,98,1810-1930``) and the register's ``rid``;
* the search behind the web page (``api/getAct.php``): DataTables JSON, 50
  rows a page. Each row's last cell is HTML whose ``title`` attributes carry
  the indexer's notes and the custodian, and whose links are the scan and the
  correction form.

Observed 2026-10-11; see docs/API-NOTES.md.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from .client import SiteError
from .text import text, tidy

BASE = "https://geneteka.genealodzy.pl/"
COVERAGE_URL = BASE + "rejestry.php?lang=pol"
SEARCH_PATH = BASE + "api/getAct.php"

#: Rows per page, as the web page asks for them.
PAGE_ROWS = 50

#: The record types a caller names, and what Geneteka calls them: marriages
#: are S (śluby).
BDM = {"B": "B", "M": "S", "D": "D"}
KIND_NAMES = {"B": "births", "S": "marriages", "D": "deaths"}
KIND_CODES = {"B": "B", "S": "M", "D": "D"}

#: Geneteka's regions: (code, name as Geneteka writes it, English).
REGIONS: tuple[tuple[str, str, str], ...] = (
    ("01ds", "dolnośląskie", "Lower Silesia"),
    ("02kp", "kujawsko-pomorskie", "Kuyavia-Pomerania"),
    ("03lb", "lubelskie", "Lublin"),
    ("04ls", "lubuskie", "Lubusz"),
    ("05ld", "łódzkie", "Łódź"),
    ("06mp", "małopolskie", "Lesser Poland"),
    ("07mz", "mazowieckie", "Masovia"),
    ("71wa", "Warszawa", "Warsaw (the city)"),
    ("08op", "opolskie", "Opole"),
    ("09pk", "podkarpackie", "Subcarpathia"),
    ("10pl", "podlaskie", "Podlachia"),
    ("11pm", "pomorskie", "Pomerania (Gdańsk)"),
    ("12sl", "śląskie", "Silesia"),
    ("13sk", "świętokrzyskie", "Holy Cross"),
    ("14wm", "warmińsko-mazurskie", "Warmia-Masuria"),
    ("15wp", "wielkopolskie", "Greater Poland; most of the Prussian Provinz Posen"),
    ("16zp", "zachodniopomorskie", "Western Pomerania"),
    ("21uk", "Ukraina", "Ukraine"),
    ("22br", "Białoruś", "Belarus"),
    ("23lt", "Litwa", "Lithuania"),
    ("25po", "Pozostałe", "Other places"),
)
REGION_NAMES = {code: name for code, name, _ in REGIONS}

#: Columns of a births or deaths row, and of a marriages row, before the
#: last cell (notes, custodian and links).
COLUMNS = {
    "B": ("year", "act", "given", "surname", "father", "mother_given", "mother_surname",
          "parish", "place"),
    "D": ("year", "act", "given", "surname", "father", "mother_given", "mother_surname",
          "parish", "place"),
    "S": ("year", "act", "groom_given", "groom_surname", "groom_parents", "bride_given",
          "bride_surname", "bride_parents", "parish"),
}  # fmt: skip

_REGISTER = re.compile(
    r'<a\s+class="([BSD])"\s+href="index\.php\?rid=(\d+)&amp;w=(\w+)&amp;op=gt"\s+'
    r'title="([^"]*)">([^<]+)</a>'
)
_TITLE = re.compile(r'title="([^"]*)"')
_CUSTODY = "Miejsce przechowywania"
_SKIPPED_TITLES = ("Indeks doda", "Zgłoś")


@dataclass(frozen=True)
class Register:
    """One register in the coverage list."""

    region: str
    parish: str
    kind: str  # B, S or D, as Geneteka writes it
    years: str
    rid: int

    def summary(self, year: int | None = None) -> dict[str, Any]:
        """The register as a tool result row."""
        out: dict[str, Any] = {
            "parish": self.parish,
            "record_type": KIND_CODES[self.kind],
            "records": KIND_NAMES[self.kind],
            "years": self.years or "(none listed)",
            "rid": self.rid,
            "region": self.region,
        }
        if year is not None:
            out["covers_year"] = covers(self.years, year)
        out["search_url"] = public_url(
            {"bdm": self.kind, "w": self.region, "rid": str(self.rid), "op": "gt", "lang": "pol"}
        )
        return out


def parse_coverage(page: str) -> list[Register]:
    """Every register in the coverage list page, in the order Geneteka lists them."""
    return [
        Register(
            region=w,
            parish=html.unescape(name).strip(),
            kind=kind,
            years=html.unescape(years).strip(),
            rid=int(rid),
        )
        for kind, rid, w, years, name in _REGISTER.findall(page)
    ]


def year_spans(years: str) -> list[tuple[int, int]]:
    """Geneteka's years as (first, last) spans.

    Geneteka shortens a year to the digits that change from the one before:
    ``1741-55,90,98,1810-1930`` is 1741-1755, 1790, 1798 and 1810-1930. A
    shortened year that would fall before the previous one moves on a
    century (``1890-99,02-05`` is 1890-1899, 1902-1905).
    """
    spans: list[tuple[int, int]] = []
    previous = ""
    for token in re.split(r"\s*,\s*", years.strip()):
        if not token:
            continue
        ends = token.split("-")
        if len(ends) > 2 or not all(e.strip().isdigit() for e in ends):
            continue
        values: list[int] = []
        for end in (e.strip() for e in ends):
            if len(end) < 4 and previous:
                full = int(previous[: len(previous) - len(end)] + end)
                if full < int(previous):
                    full += 10 ** len(end)
                end = str(full)
            values.append(int(end))
            previous = end
        spans.append((values[0], values[-1]))
    return spans


def covers(years: str, year: int) -> bool:
    """Whether Geneteka lists ``year`` as indexed in this register."""
    return any(first <= year <= last for first, last in year_spans(years))


def public_url(query: dict[str, str]) -> str:
    """The address of a Geneteka search page a person can open."""
    return BASE + "index.php?" + urlencode(query)


def search_query(
    *,
    bdm: str,
    region: str,
    rid: int | None,
    surname: str,
    given: str,
    surname2: str,
    given2: str,
    year_from: int | None,
    year_to: int | None,
    exact: bool,
) -> dict[str, str]:
    """The query Geneteka's own search page sends, as the script did."""
    query = {
        "op": "gt",
        "lang": "pol",
        "bdm": bdm,
        "w": region,
        "rid": str(rid) if rid else bdm,
        "search_lastname": surname,
        "search_name": given,
        "search_lastname2": surname2,
        "search_name2": given2,
        "from_date": str(year_from) if year_from else "",
        "to_date": str(year_to) if year_to else "",
    }
    if exact:
        query["exac"] = "1"
    return query


def search_url(query: dict[str, str], page: int) -> str:
    """The API address for one page of a search."""
    paging = {"draw": "1", "start": str((page - 1) * PAGE_ROWS), "length": str(PAGE_ROWS)}
    return SEARCH_PATH + "?" + urlencode({**paging, **query})


def parse_search(raw: str, bdm: str, url: str = "") -> dict[str, Any]:
    """Decode one page of search results.

    Returns ``total``, ``rows`` and ``searched`` (the registers Geneteka
    says it searched; empty when it searched a whole region).

    Raises
    ------
    SiteError
        ``unexpected_answer`` if the answer is not the JSON the page reads,
        or a row does not have the columns expected for its record type.
    """
    try:
        data = json.loads(raw)
    except ValueError:
        raise SiteError(
            "unexpected_answer",
            "Geneteka answered with something that is not its search JSON"
            + (" (a web page)" if raw.lstrip()[:1] == "<" else ""),
            url=url,
        ) from None
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise SiteError("unexpected_answer", "Geneteka's answer has no rows list", url=url)
    columns = COLUMNS[bdm]
    rows = []
    for row in data["data"]:
        if not isinstance(row, list) or len(row) != len(columns) + 1:
            raise SiteError(
                "unexpected_answer",
                f"a Geneteka row has {len(row) if isinstance(row, list) else 'no'} cells, "
                f"not the {len(columns) + 1} expected; the site may have changed",
                url=url,
            )
        rows.append(_row(row, columns))
    searched = []
    parishes = data.get("parishes")
    if isinstance(parishes, dict):
        for region, entries in parishes.items():
            for entry in entries or []:
                if isinstance(entry, list) and len(entry) >= 2:
                    searched.append({"rid": entry[0], "parish": entry[1], "region": region})
    total = data.get("recordsTotal", 0)
    return {"total": int(total) if str(total).isdigit() else 0, "rows": rows, "searched": searched}


def _row(row: list, columns: tuple[str, ...]) -> dict[str, Any]:
    """One search row: its columns, then what the last cell's markup says."""
    out: dict[str, Any] = {}
    notes: list[str] = []
    for name, cell in zip(columns, row[:-1], strict=True):
        raw = str(cell)
        value = text(raw)
        if value:
            out[name] = int(value) if name == "year" and value.isdigit() else value
        for title in _TITLE.findall(raw):
            for part in _title_parts(title):
                notes.append(f"{name}: {part}")
    extras = str(row[-1])
    custodian, address = "", ""
    for title in _TITLE.findall(extras):
        parts = _title_parts(title)
        if not parts:
            continue
        if parts[0].startswith(_CUSTODY):
            head = parts[0].split(":", 1)[1].strip() if ":" in parts[0] else ""
            rest = ([head] if head else []) + parts[1:]
            custodian = rest[0] if rest else ""
            address = ", ".join(rest[1:])
        elif not parts[0].startswith(_SKIPPED_TITLES):
            notes.extend(parts)
    links: list[str] = []
    finder = ""
    for attrs, inner in re.findall(r"<a\b([^>]*)>(.*?)</a>", extras, re.S):
        href_m = re.search(r'href\s*=\s*"([^"]*)"', attrs)
        if not href_m:
            continue
        href = html.unescape(href_m.group(1))
        if "fix.php" in href:
            gid = re.search(r"gid=(\d+)", href)
            finder = gid.group(1) if gid else finder
            continue
        if "user.php" in href or "images/z.png" in inner or "images/a.png" in inner:
            continue
        if href.startswith(("http://", "https://")):
            links.append(href)
    if notes:
        out["notes"] = notes
    if custodian:
        out["custodian"] = custodian
    if address:
        out["custodian_address"] = address
    if links:
        out["scan_links"] = links
    if finder:
        out["geneteka_id"] = finder
    return out


def _title_parts(title: str) -> list[str]:
    """A title attribute split on the carriage returns Geneteka puts between notes."""
    value = html.unescape(title)
    return [tidy(p) for p in re.split(r"[\r\n]+", value) if tidy(p)]
