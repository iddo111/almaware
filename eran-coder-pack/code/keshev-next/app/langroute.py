def _has_real_latin_word(text: str) -> bool:
    """Check if any whitespace-split token is >=2 ASCII letters (no digits, no spaces)."""
    for token in text.split():
        # Filter only ASCII letters a-zA-Z
        letters_only = ''.join(c for c in token if 'a' <= c.lower() <= 'z')
        if len(letters_only) >= 2:
            return True
    return False

def route_language(text: str, detected_lang: str, avg_logprob: float) -> str | None:
    # Rule 1: Hallucination detection
    if avg_logprob < -1.2 and len(text.split()) <= 2 and not _has_real_latin_word(text):
        return None

    # Rule 2: English detection override: >50% Hebrew letters
    if detected_lang == 'en':
        hebrew_chars = sum(1 for c in text if '\u05D0' <= c <= '\u05EA')
        total_letters = sum(1 for c in text if c.isalpha())
        if total_letters > 0 and hebrew_chars / total_letters > 0.5:
            return 'he'

    # Rule 3: Any Hebrew letters -> Hebrew
    if any('\u05D0' <= c <= '\u05EA' for c in text):
        return 'he'

    # Rule 4: Real English words (a-z present, at least one word len>=2)
    # Check for presence of Latin letters and real words (>=2 letters)
    has_latin = any('a' <= c.lower() <= 'z' for c in text)
    if has_latin and _has_real_latin_word(text):
        return 'en'

    # Rule 5: Russian passes through
    if detected_lang == 'ru':
        return 'ru'

    # Rule 6: Low confidence with no clear signal -> default to Hebrew
    return 'he'

if __name__ == '__main__':
    assert route_language('hello world','en',-0.4)=='en'
    assert route_language('this is a test','en',-0.3)=='en'
    assert route_language('שלום hello','en',-0.5)=='he'
    assert route_language('אבג','en',-1.6) is None
    print('LANGROUTE OK')
