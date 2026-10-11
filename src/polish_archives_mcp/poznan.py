"""The Poznań Project: marriages of 1800-1899 in Wielkopolska and Kujawy.

The search page posts a form to ``getresults.php`` and gets back an HTML
fragment: a statistics box, then one block per marriage. Given names are not
typed in: the form offers name groups ("Adalbert(us) / Wojciech"), each a
number, so a given name has to be matched to its group first. Each entry
links a page saying which archive holds the original register
(``pages/arch_location/archN.htm``); those pages are fixed, and the ones seen
on 2026-10-11 are in :data:`ARCHIVES`.

Observed 2026-10-11; see docs/API-NOTES.md.
"""

from __future__ import annotations

import html
import re
from typing import Any

from .client import SiteError
from .text import fold, text, tidy

BASE = "https://poznan-project.psnc.pl/"
RESULTS_URL = BASE + "getresults.php"
ARCHIVE_PAGE = BASE + "pages/arch_location/arch{}.htm"

#: The years the project indexes.
FIRST_YEAR, LAST_YEAR = 1800, 1899

#: The form's confession values.
CONFESSIONS = {"any": "0", "catholic": "1", "protestant": "2", "civil": "3"}

#: Who holds the original register, by archive-page number, as the pages
#: said on 2026-10-11 (their English sentence). A number not here is read
#: from its page and cached.
ARCHIVES: dict[int, str] = {
    1: "Archdiocesan Archive in Poznań, Poland",
    2: "National Archive in Poznań, Poland",
    3: "Diocesan Archive in Zielona Gora, Poland",
    4: "Archdiocesan Archive in Gniezno, Poland",
    5: "National Archive in Bydgoszcz, Poland",
    6: "Diocesan Archive in Pelplin, Poland",
    7: "Evangelisches Zentralarchiv in Berlin, Germany",
    8: "Sächsisches Staatsarchiv in Leipzig, Germany (microfilm only)",
    9: "Brandenburgisches Landeshauptarchiv in Potsdam, Germany",
    10: "respective Roman Catholic parish in Poland",
    11: "Archive in Poznań, Poland (only as civil duplicate, the original book is in the "
    "Archdiocesan Archive in Poznan)",
    12: "Diocesan Archive in Włocławek, Poland",
    13: "National Archive in Gorzow Wielkopolski, Poland",
    14: "National Archive in Lodz, Poland",
    15: "Diocesan Archive in Toruń, Poland",
    16: "Geheimes Staatsarchiv Preussischer Kulturbesitz in Berlin, Germany",
    17: "National Archive in Kalisz, Poland",
    18: "State Archive in Włocławek, Poland",
    19: "National Archive in Inowroclaw, Poland",
    20: "National Archive in Pila, Poland",
    21: "National Archive in Konin, Poland",
    22: "State Archive in Koszalin, Poland",
    23: "Landesarchiv Berlin, Germany (previously in Standesamt I)",
    24: "Archdiocesan Archive in Lodz, Poland",
    25: "Archdiocesan Archive in Czestochowa, Poland",
    26: "Archdiocesan Archive in Wrocław, Poland",
    27: "National Archive in Leszno, Poland",
    28: "Diocesan Archive in Koszalin, Poland",
    29: "State Archive in Zielona Gora, Poland",
    30: "State Archive in Szczecin, Poland",
    31: "Diocesan Archive in Opole, Poland",
    32: "State Archive in Opole, Poland",
    33: "Regional Museum in Sieradz, Poland",
    34: "Landesarchiv in Greifswald, Germany",
    35: "Diocesan Archive in Lowicz, Poland",
    36: "State Archive in Wrocław, Poland",
    37: "State Archive in Torun, Poland",
    39: "Archiv des Katholischen Militärbischofs, in Berlin, Germany",
    40: "Szczecinek filial of the State Archive in Koszalin, Poland",
}

_STATS_EXACT = re.compile(r"Wyniki zgodne:\s*(\d+)")
_STATS_ABOVE = re.compile(r"Wyniki powyżej progu\s*(\d+)%:\s*(\d+)")
_TOO_MANY = "Zbyt duża liczba wyników"
_NONE = "Nie znaleziono pasujących zapisów"
_LABELS = {
    "parafia katolicka": "Catholic parish",
    "parafia ewangelicka": "Protestant parish",
    "urząd stanu cywilnego": "civil registry office",
}


class AmbiguousName(ValueError):
    """A given name matches more than one name group."""

    def __init__(self, given: str, labels: list[str]):
        self.given = given
        self.labels = labels
        super().__init__(f"{given!r} matches {len(labels)} name groups")


def name_groups(form: str, select: str) -> list[tuple[str, str]]:
    """The (value, label) name groups of one first-name select, without 'any'."""
    m = re.search(rf'<select[^>]*name="{re.escape(select)}"[^>]*>(.*?)</select>', form, re.S)
    if not m:
        return []
    options = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)', m.group(1))
    return [(v, tidy(html.unescape(label))) for v, label in options if v not in ("", "0")]


def group_forms(label: str) -> set[str]:
    """Every spelling a name-group label stands for, folded.

    ``Adalbert(us) / Wojciech`` stands for adalbert, adalbertus and wojciech;
    ``Apol(l)onia`` for apolonia and apollonia.
    """
    forms: set[str] = set()
    for part in re.split(r"[/,]", label):
        part = part.strip()
        if not part:
            continue
        forms.add(fold(re.sub(r"\(([^)]*)\)", "", part)).strip())
        forms.add(fold(re.sub(r"\(([^)]*)\)", r"\1", part)).strip())
    return {f for f in forms if f}


def pick_group(groups: list[tuple[str, str]], given: str) -> str | None:
    """The value of the name group ``given`` belongs to, or None if none fits.

    An exact spelling wins. Otherwise a name that a group's spelling begins
    (Wawrzyniec for Wawrzyn, Johannes for Johann) or that begins a group's
    spelling (Adalb for Adalbertus) fits, if only one group fits that way.

    Raises
    ------
    AmbiguousName
        If no group matches exactly and more than one matches by beginning.
    """
    g = fold(given).strip()
    if not g:
        return None
    for value, label in groups:
        if g in group_forms(label) or g == fold(label):
            return value
    loose = [
        (value, label)
        for value, label in groups
        if any(
            (f.startswith(g) and len(g) >= 4) or (g.startswith(f) and len(f) >= 5)
            for f in group_forms(label)
        )
    ]
    if len(loose) == 1:
        return loose[0][0]
    if len(loose) > 1:
        raise AmbiguousName(given, [label for _, label in loose])
    return None


def parse_results(page: str, url: str = RESULTS_URL) -> dict[str, Any]:
    """Decode a results fragment.

    Returns ``exact`` and ``above_threshold`` (the counts the statistics box
    gives), ``too_many`` (the site listed no entries because there were too
    many), and ``rows``.

    Raises
    ------
    SiteError
        ``unexpected_answer`` if the fragment has neither entries nor one of
        the site's own "nothing found" or "too many" messages.
    """
    exact = _STATS_EXACT.search(page)
    above = _STATS_ABOVE.search(page)
    blocks = re.split(r'<div class="small-toolbox">', page)[1:]
    rows = [row for row in (_row(b) for b in blocks) if row]
    too_many = _TOO_MANY in page and not rows
    if not rows and not too_many and _NONE not in page:
        raise SiteError(
            "unexpected_answer",
            "the Poznań Project's answer has no entries and no 'nothing found' message; "
            "the site may have changed",
            url=url,
        )
    return {
        "exact": int(exact.group(1)) if exact else (0 if not rows else None),
        "above_threshold": int(above.group(2)) if above else (0 if not rows else None),
        "too_many": too_many,
        "rows": rows,
    }


def _row(block: str) -> dict[str, Any] | None:
    h3 = re.search(r'<h3 class="result\s*([^"]*)">(.*?)</h3>', block, re.S)
    if not h3:
        return None
    out: dict[str, Any] = {}
    ident = re.search(r"new_comment_for_(\d+)|showNewCommentForm\('(\d+)'", block)
    if ident:
        out["poznan_id"] = ident.group(1) or ident.group(2)
    heading = h3.group(2)
    parts = re.search(r"^(.*?)<b>(.*?)</b>(.*)$", heading, re.S)
    if parts:
        label = text(parts.group(1))
        out["register"] = _LABELS.get(label.lower(), label)
        out["parish"] = text(parts.group(2)).rstrip(", ")
        entry = re.search(r"wpis\s*(.+?)\s*/\s*(\d{4})", text(parts.group(3)))
        if entry:
            out["entry"] = entry.group(1)
            out["year"] = int(entry.group(2))
    else:
        out["heading"] = text(heading)
    out["match"] = "exact" if h3.group(1).startswith("exact") else "approximate"
    for role in ("groom", "bride"):
        li = re.search(rf'<li class="{role}[^"]*">(.*?)</li>', block, re.S)
        if not li:
            continue
        inner = li.group(1)
        # The bar image is rounded to tens; the figure after it is exact.
        bar = re.search(r"bar(\d+)\.gif[^>]*>\s*(?:(\d{1,3})\s*%)?", inner)
        inner = re.sub(r"<img[^>]*bar\d+\.gif[^>]*>\s*(?:\d{1,3}\s*%)?", " ", inner)
        out[role] = text(inner)
        if bar:
            out[f"{role}_similarity"] = int(bar.group(2) or bar.group(1))
    comments = []
    for li in re.findall(r'<li class="comment"[^>]*>(.*?)</li>', block, re.S):
        said = re.search(r"<i>(.*?)</i>", li, re.S)
        when = re.search(r"\((\d{2}-\d{2}-\d{4})\)", li)
        if said:
            comment = {"text": text(said.group(1))}
            if when:
                comment["date"] = when.group(1)
            comments.append(comment)
    if comments:
        out["comments"] = comments
    arch = re.search(r'href="pages/arch_location/arch(\d+)\.htm', block)
    if arch:
        out["archive_page"] = int(arch.group(1))
    return out


def parse_archive_page(page: str) -> str | None:
    """Who holds the original, from an archive-location page's English sentence."""
    plain = text(page)
    m = re.search(
        r"The original record (?:\(microfilm only!\) )?for this marriage is held (?:in|at) "
        r"(?:the )?(.*?)\.(?:\s|$)",
        plain,
    )
    if not m:
        return None
    value = tidy(m.group(1))
    return value + (" (microfilm only)" if "microfilm only" in plain else "")
