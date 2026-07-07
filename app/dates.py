"""Best-effort date parsing for free-text tournament date strings."""
from __future__ import annotations

import re

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_date_range(text: str | None) -> tuple[str | None, str | None]:
    """Parse strings like 'Aug 22-23, 2026' or 'Sep 12-13 2026' or 'Nov 12-15'.

    Returns (start_iso, end_iso); either may be None. Year defaults handled by caller.
    """
    if not text:
        return None, None
    low = text.lower()
    # Cross-month range: 'July 31 - August 2, 2026'
    m = re.search(
        r"([a-z]{3,9})\.?\s+(\d{1,2})\s*[-–]\s*([a-z]{3,9})\.?\s+(\d{1,2}),?\s*(\d{4})", low
    )
    if m:
        mon1, d1, mon2, d2, yr = m.groups()
        m1, m2 = _MONTHS.get(mon1[:3]), _MONTHS.get(mon2[:3])
        if m1 and m2:
            y = int(yr)
            return (f"{y:04d}-{m1:02d}-{int(d1):02d}", f"{y:04d}-{m2:02d}-{int(d2):02d}")
    m = re.search(r"([a-z]{3,9})\.?\s+(\d{1,2})\s*[-–]\s*(\d{1,2})(?:,?\s*(\d{4}))?", low)
    if m:
        mon, d1, d2, yr = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        month = _MONTHS.get(mon[:3])
        if month and yr:
            y = int(yr)
            return (f"{y:04d}-{month:02d}-{d1:02d}", f"{y:04d}-{month:02d}-{d2:02d}")
        if month:
            return (f"{month:02d}-{d1:02d}", f"{month:02d}-{d2:02d}")
    # single date: 'Aug 22, 2026'
    m = re.search(r"([a-z]{3,9})\.?\s+(\d{1,2}),?\s*(\d{4})", low)
    if m:
        month = _MONTHS.get(m.group(1)[:3])
        if month:
            y, d = int(m.group(3)), int(m.group(2))
            return (f"{y:04d}-{month:02d}-{d:02d}", None)
    return None, None
