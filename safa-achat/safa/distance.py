"""Edit distance, normalized similarity, and alignment (stdlib only)."""
from __future__ import annotations


def levenshtein(a: str, b: str) -> int:
    """Classic dynamic-programming edit distance."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def norm_sim(a: str, b: str) -> float:
    """Normalized similarity in [0, 1]: 1 - dist / max(len)."""
    if not a and not b:
        return 1.0
    m = max(len(a), len(b))
    if m == 0:
        return 1.0
    return 1.0 - levenshtein(a, b) / m


def align(a: str, b: str) -> list[tuple[str, str]]:
    """Global alignment (Needleman–Wunsch with unit costs).

    Returns a list of (symbol_a, symbol_b) column pairs where '-' marks a gap.
    Used to collect sound-correspondence pairs for the comparative module.
    """
    n, m = len(a), len(b)
    # DP table of costs
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
    for j in range(1, m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + (a[i - 1] != b[j - 1]),
            )
    # backtrace
    cols: list[tuple[str, str]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (a[i - 1] != b[j - 1]):
            cols.append((a[i - 1], b[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            cols.append((a[i - 1], "-"))
            i -= 1
        else:
            cols.append(("-", b[j - 1]))
            j -= 1
    cols.reverse()
    return cols
