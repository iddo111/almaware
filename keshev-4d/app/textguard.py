# app/textguard.py
from typing import Optional, Tuple

WHITELIST = ('he', 'en')
FLOOR = -0.6
HALLUCINATIONS = frozenset({
    'thank you.',
    'thanks for watching!',
    'you',
    'תודה רבה.',
    'תודה שצפיתם'
})

def verdict(text: str, avg_logprob: Optional[float], lang: Optional[str]) -> Tuple[bool, str]:
    """
    Returns (is_ok, reason).
    is_ok: True if text passes all guards, False otherwise.
    reason: one of 'empty', 'lang', 'logprob', 'hallucination', 'ok'.
    """
    # 1. empty/whitespace
    if not text or text.isspace():
        return (False, 'empty')
    # 2. language not in whitelist
    if lang not in WHITELIST:
        return (False, 'lang')
    # 3. logprob below floor (only when not None)
    if avg_logprob is not None and avg_logprob < FLOOR:
        return (False, 'logprob')
    # 4. hallucination phrases (normalized)
    normalized = text.strip().lower()
    if normalized in HALLUCINATIONS:
        return (False, 'hallucination')
    # 5. passed all checks
    return (True, 'ok')
