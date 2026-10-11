"""BaSIA: the Wielkopolskie Towarzystwo Genealogiczne "Gniazdo"'s archival index.

The search is the site's own extended-search form, posted to ``/en/``; the
answer is a whole page. Each entry is a ``result_box``: on the left the
register (place, kind of office, record type, year, book) and the people in
the entry, with how closely each matched; on the right the archive, the call
number and scan as BaSIA writes them, a link to the unit on Szukaj w
Archiwach, and BaSIA's own id and permalink. A page lists at most 250
entries and says so when there are more.

Observed 2026-10-11; see docs/API-NOTES.md.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from .client import SiteError
from .text import text, tidy

BASE = "https://www.basia.famula.pl"
SEARCH_URL = BASE + "/en/"

#: The form's values for the kind of office and the kind of record.
UNITS = {"any": "any", "usc": "usc", "kat": "kat", "ewa": "ewa", "other": "other"}
RECORDS = {"any": "any", "birth": "a", "marriage": "b", "death": "c", "other": "z"}

#: The earliest year the form offers.
FIRST_YEAR = 1577

#: Carried on every row, because BaSIA's call number is easy to cite by mistake.
CALL_NUMBER_WARNING = (
    "BaSIA's middle (series) number can differ from the archive's: cite the Sygnatura "
    "shown on the unit page, not this call number."
)

#: Said of a row whose link is on the retired szukajwarchiwach.pl domain.
RETIRED_LINK_NOTE = (
    "BaSIA links this entry to the retired szukajwarchiwach.pl, which no longer opens. "
    "Find the unit on www.szukajwarchiwach.gov.pl in a browser (the fonds page lists its "
    "units) and take the Sygnatura and scan from there."
)

_SWA_UNIT = re.compile(
    r"^https?://(?:www\.)?szukajwarchiwach\.gov\.pl/jednostka/-/jednostka/(\d+)(?:#scan(\d+))?"
)
_SWA_RETIRED = re.compile(
    r"^https?://(?:www\.)?szukajwarchiwach\.pl/(\d+)/(\d+)/(\d+)/([\d.]+)/(\d+)"
)
_TOTAL = re.compile(r"wszystkie pasuj(?:\\u0105|ą)ce wpisy:\s*(\d+)")
_BOX = re.compile(
    r"<div class='result_box[^']*' id='resboxid(\d+)'>(.*?)"
    r"(?=<div class='result_box|<div id='resgroup|\Z)",
    re.S,
)
_NONE = ("No search results for your query", "Brak wyników")


def search_form(
    *,
    people: list[tuple[str, str]],
    place: str,
    distance_km: int,
    year_from: int | None,
    year_to: int | None,
    similarity: int,
    unit: str,
    record: str,
    today: date,
) -> dict[str, str]:
    """The form BaSIA's extended search posts, as the script sent it."""
    form = {
        "p_count": str(len(people)),
        "od": str(year_from or FIRST_YEAR),
        "do": str(year_to or today.year),
        "placename": place,
        "distance": str(distance_km),
        "type_unit": UNITS[unit],
        "type_record": RECORDS[record],
        "datefrom": "2011-01-28",
        "dateto": today.isoformat(),
        "showplaces": "block" if place else "none",
        "showtype": "block",
        "showdate": "none",
        "search_ext": "szukaj",
        "search_ext_button": "Search",
    }
    for i, (given, surname) in enumerate(people):
        form.update(
            {
                f"fname{i}": given,
                f"lname{i}": surname,
                f"sex{i}": "any",
                f"type{i}": "any",
                f"sim{i}": str(similarity),
            }
        )
    return form


def parse_results(page: str, url: str = SEARCH_URL) -> dict[str, Any]:
    """Decode a results page: ``total``, ``truncated`` and ``rows``.

    Raises
    ------
    SiteError
        ``unexpected_answer`` if the page has no entries and no "no results"
        message.
    """
    rows = [_row(ident, body) for ident, body in _BOX.findall(page)]
    total_m = _TOTAL.search(page)
    if not rows and not any(marker in page for marker in _NONE):
        raise SiteError(
            "unexpected_answer",
            "BaSIA's answer has no entries and no 'no results' message; the site may have changed",
            url=url,
        )
    total = int(total_m.group(1)) if total_m else len(rows)
    truncated = bool(re.search(r"class=['\"]results-truncated", page)) or (
        "exceeded maximum value" in page
    )
    return {"total": total, "truncated": truncated or total > len(rows), "rows": rows}


def _row(ident: str, body: str) -> dict[str, Any]:
    out: dict[str, Any] = {"basia_id": ident}
    left_m = re.search(r"<div class='lbox'>(.*?)</div>\s*<div class='rbox'>", body, re.S)
    right_m = re.search(r"<div class='rbox'>(.*)", body, re.S)
    left = left_m.group(1) if left_m else ""
    right = right_m.group(1) if right_m else body
    left = re.sub(
        r"<div class='progress-container' title='[^']*?(\d+)%'>\s*<div[^>]*>\s*</div>\s*</div>",
        r" [\1%]",
        left,
    )
    sections = re.split(r"<br>\s*<br>", left)
    unit = re.search(r"<span[^>]*>\s*<a [^>]*>([^<]+)</a>\s*</span>", sections[0])
    if unit:
        out["unit"] = tidy(unit.group(1))
        header = text(sections[0][unit.end() :])
    else:
        header = text(sections[0])
    head = re.match(r"\((.*?)\)\s*-\s*(.*?),\s*year\s*(\d{3,4})\s*,?\s*(.*)$", header)
    if head:
        out["register"] = head.group(1)
        out["record"] = head.group(2)
        out["year"] = int(head.group(3))
        rest = head.group(4)
        entry = re.search(r"wpis nr\s*([^,\s]+)", rest)
        if entry:
            out["entry"] = entry.group(1)
            rest = rest.replace(entry.group(0), "")
        book = tidy(rest)
        if book:
            out["book"] = book
    elif header:
        out["register"] = header
    if len(sections) > 1:
        out["persons"] = text(sections[1])
    for section in sections[2:]:
        label_m = re.match(r"\s*<b>(.*?)</b>\s*:?", section, re.S)
        if not label_m:
            continue
        label = text(label_m.group(1)).lower()
        value = text(section[label_m.end() :])
        if not value:
            continue
        if label.startswith("indexer notes"):
            out["indexer_notes"] = value
        elif label.startswith("other people"):
            out["other_people"] = value
        else:
            out.setdefault("details", {})[label] = value
    archive = re.search(r"<a href='/showbox\.php\?id=([^&']+)[^']*'[^>]*>([^<]+)</a>", right)
    if archive:
        out["archive"] = tidy(archive.group(2))
        out["archive_code"] = archive.group(1)
    link = re.search(
        r"<a href='(https?://[^']*szukajwarchiwach[^']*)'[^>]*>\s*([^<]+?)\s*</a>", right
    )
    if link:
        href, label = link.group(1), tidy(link.group(2))
        call = re.match(r"^(.*?),\s*scan\s*(\S+)$", label)
        out["basia_call_number"] = call.group(1) if call else label
        if call:
            out["scan"] = int(call.group(2)) if call.group(2).isdigit() else call.group(2)
        _unit_link(out, href)
    else:
        after = right[archive.end() :] if archive else right
        call_text = text(after.split("indexed by")[0])
        if call_text:
            out["basia_call_number"] = call_text
        out["unit_url"] = None
    permalink = re.search(r"href='(/record/[A-Za-z0-9_=-]+)'", right)
    if permalink:
        out["basia_url"] = BASE + permalink.group(1)
    out["call_number_warning"] = CALL_NUMBER_WARNING
    return out


def _unit_link(out: dict[str, Any], href: str) -> None:
    """The unit address on the current domain, or a note about a retired link."""
    current = _SWA_UNIT.match(href)
    if current:
        scan = current.group(2) or (str(out["scan"]) if isinstance(out.get("scan"), int) else "")
        out["unit_url"] = (
            f"https://www.szukajwarchiwach.gov.pl/jednostka/-/jednostka/{current.group(1)}"
            + (f"#scan{scan}" if scan else "")
        )
        return
    out["unit_url"] = None
    retired = _SWA_RETIRED.match(href)
    out["retired_link"] = href
    if retired:
        out["reference_in_link"] = "/".join(retired.groups())
    out["unit_url_note"] = RETIRED_LINK_NOTE
