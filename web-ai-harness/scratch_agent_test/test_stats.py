from stats import mean, median, pct_change


def test_mean():
    assert mean([1, 2, 3]) == 2


def test_median_odd():
    assert median([3, 1, 2]) == 2


def test_median_even():
    assert median([1, 2, 3, 4]) == 2.5


def test_pct_change():
    assert pct_change(100, 150) == 50.0


def test_mean_empty_returns_zero():
    assert mean([]) == 0
