"""DOM value extractor for Phase C route crawler.

Parses the text content of ``data-validator-id`` elements into ``Decimal``
values (or ``None`` for intentionally-absent values).

Parse contracts
---------------
"+12.5%"           → Decimal("0.125")   (strip sign, divide by 100)
"-3.2%"            → Decimal("-0.032")
"₹1,23,456.78"    → Decimal("123456.78") (Indian lakh formatting)
"1,234.56"         → Decimal("1234.56")
"0.85"             → Decimal("0.85")     (bare fraction — conviction score)
"85"               → Decimal("85")       (integer — rank / count)
"Overweight"       → "Overweight"        (categorical — returned as str)
"Yes" / "No"       → "Yes" / "No"        (boolean display)
"—" / "–" / ""    → None               (explicitly absent — skip diff)
"Loading..."       → ExtractError        (data not yet loaded)
"N/A"              → None

Raises ``ExtractError`` only for ``Loading...`` text.  All other
unparseable text is returned as a plain ``str`` for categorical comparison.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

ParsedValue = Decimal | str | None


class ExtractError(Exception):
    """DOM element contains a loading placeholder, not a real value."""

    def __init__(self, raw: str) -> None:
        super().__init__(f"Loading placeholder not yet resolved: {raw!r}")
        self.raw = raw


_LOADING_PATTERNS = re.compile(
    r"loading\.\.\.|loading|fetching|please wait",
    re.IGNORECASE,
)
_ABSENT_VALUES = frozenset({"—", "–", "-", "n/a", "na", "nil", "null", ""})
_PCT_RE = re.compile(r"^([+-]?\d[\d,]*\.?\d*)\s*%$")
_CURRENCY_RE = re.compile(r"^₹\s*([\d,]+\.?\d*)$")
_NUMERIC_RE = re.compile(r"^[+-]?\d[\d,]*\.?\d*$")


def parse_dom_value(raw: str) -> ParsedValue:
    """Parse a DOM text value into a typed Python value.

    Args:
        raw: Text content of a ``data-validator-id`` element, stripped.

    Returns:
        ``Decimal`` for numeric/percentage/currency values.
        ``str`` for categorical values (states, labels).
        ``None`` for intentionally-absent values (em-dash, N/A, empty).

    Raises:
        ExtractError: If ``raw`` contains a loading placeholder.
    """
    text = raw.strip()

    if _LOADING_PATTERNS.search(text):
        raise ExtractError(text)

    if text.lower() in _ABSENT_VALUES:
        return None

    # Percentage: "+12.5%" → Decimal("0.125")
    pct_match = _PCT_RE.match(text)
    if pct_match:
        numeric_str = pct_match.group(1).replace(",", "")
        try:
            return Decimal(numeric_str) / Decimal("100")
        except InvalidOperation:
            pass

    # Indian currency: "₹1,23,456.78" → Decimal("123456.78")
    cur_match = _CURRENCY_RE.match(text)
    if cur_match:
        numeric_str = cur_match.group(1).replace(",", "")
        try:
            return Decimal(numeric_str)
        except InvalidOperation:
            pass

    # Plain numeric (possibly with commas): "1,234.56" → Decimal("1234.56")
    if _NUMERIC_RE.match(text):
        numeric_str = text.replace(",", "")
        try:
            return Decimal(numeric_str)
        except InvalidOperation:
            pass

    # Categorical string — return as-is for exact comparison
    return text
