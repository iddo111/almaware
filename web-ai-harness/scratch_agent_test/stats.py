"""Small stats helpers used by the harness reporting layer."""


def mean(values):
    """Return the arithmetic mean of *values*.

    If *values* is empty, return ``0`` instead of raising ``ZeroDivisionError``.
    """
    if not values:
        return 0
    return sum(values) / len(values)


def median(values):
    """Return the median of *values*.

    For an even number of elements, returns the average of the two middle values.
    """
    s = sorted(values)
    n = len(s)
    if n == 0:
        raise ValueError("median of empty sequence")
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    # even length: average the two middle values
    return (s[mid - 1] + s[mid]) / 2


def pct_change(old, new):
    return (new - old) / old * 100.0
