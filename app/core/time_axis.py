"""Which candle dates get a label on the time axis, and what each label says.

Candles sit one per slot (0, 1, 2, ...), so weekends and holidays leave no gaps. Labels go where a new year,
month, week or day starts (so a label never repeats), using the finest unit that fits the available width.
"""
import numpy as np
import pandas as pd

PIXELS_PER_LABEL = 90


def _year(dates):
    return dates.year


def _month(dates):
    return dates.year * 12 + dates.month


def _week(dates):
    return (dates - pd.to_timedelta(dates.day_of_week, unit='D')).normalize().asi8


def _day(dates):
    return dates.normalize().asi8


# Coarsest to finest: (group dates by, label format, marker group, label format when the marker changes).
# E.g. month labels read "Oct", "Nov", but "2026" where a new year begins.
LEVELS = [
    (_year, '%Y', None, '%Y'),
    (_month, '%b', _year, '%Y'),
    (_week, '%d', _month, '%b'),
    (_day, '%d', _month, '%b'),
]


def _group_starts(dates: pd.DatetimeIndex, group) -> list[int]:
    """Positions where a new year/month/week/day begins (vectorised: fast even for 60 years of days)."""
    keys = np.asarray(group(dates))
    return (np.flatnonzero(keys[1:] != keys[:-1]) + 1).tolist()


def tick_labels(dates: pd.DatetimeIndex, min_slot: float, max_slot: float, width_px: float) -> dict[int, str]:
    """{slot: label} for the slots between min_slot and max_slot, empty if too little is in view."""
    first, last = max(int(np.ceil(min_slot)), 0), min(int(max_slot), len(dates) - 1)
    if last <= first:
        return {}
    max_labels = max(2, int(width_px / PIXELS_PER_LABEL))
    shown = dates[first:last + 1]
    # Use the finest unit (day, week, month, year) that needs at most every other start labelled.
    level, starts = 0, _group_starts(shown, LEVELS[0][0])
    for candidate in range(len(LEVELS) - 1, -1, -1):
        candidate_starts = _group_starts(shown, LEVELS[candidate][0])
        if len(candidate_starts) <= 2 * max_labels:
            level, starts = candidate, candidate_starts
            break
    starts = starts[::int(np.ceil(len(starts) / max_labels)) or 1]

    _, plain_format, marker, marker_format = LEVELS[level]
    marker_keys = np.asarray(marker(shown)) if marker else None
    labels: dict[int, str] = {}
    previous = None
    for i in starts:
        # Marker label if the year (or month) changed since the previous label, or at this very date.
        reference = previous if previous is not None else i - 1
        marked = marker_keys is not None and marker_keys[i] != marker_keys[reference]
        labels[first + i] = f'{shown[i]:{marker_format if marked else plain_format}}'
        previous = i
    return labels
