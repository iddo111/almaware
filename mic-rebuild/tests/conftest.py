"""KESHEV pytest configuration.

Registers the `focus_intrusive` marker (focus-courtesy guardrail, wave 4):
tests carrying it steal global foreground focus / flash windows. They are
additionally env-gated on KESHEV_FOCUS_INTRUSIVE=1 so the normal full suite
never grabs Iddo's focus while he works. Run them explicitly, briefly, at
most once per change:

    KESHEV_FOCUS_INTRUSIVE=1 python -m pytest tests -m focus_intrusive
"""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "focus_intrusive: steals global foreground focus / flashes windows; "
        "env-gated on KESHEV_FOCUS_INTRUSIVE=1 (focus-courtesy guardrail)",
    )
