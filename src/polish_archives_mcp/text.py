"""Small text helpers shared by the parsers."""

from __future__ import annotations

import html
import re
import unicodedata


def text(fragment: str) -> str:
    """An HTML fragment as one line of plain text: tags dropped, entities decoded."""
    fragment = re.sub(r"<(script|style)\b.*?</\1>", " ", fragment, flags=re.S | re.I)
    fragment = re.sub(r"<br\s*/?>", " ; ", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    return tidy(html.unescape(fragment))


def tidy(value: str) -> str:
    """Collapse whitespace and the spaces the sites leave before punctuation."""
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s+([,;:)])", r"\1", value)
    value = re.sub(r"\(\s+", "(", value)
    value = re.sub(r"(;\s*)+;", ";", value)
    return value.strip(" ;,")


def fold(value: str) -> str:
    """Lower case with diacritics removed, so 'Łódź' matches 'lodz'."""
    value = unicodedata.normalize("NFKD", value.replace("ł", "l").replace("Ł", "L"))
    return "".join(c for c in value if not unicodedata.combining(c)).lower()
