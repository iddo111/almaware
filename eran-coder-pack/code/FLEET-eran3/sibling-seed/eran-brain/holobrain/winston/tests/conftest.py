"""Test paths: the organ dir and alma-language, nothing else. No torch here."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ORGAN = os.path.dirname(HERE)
for p in (ORGAN, "D:/CLAUDE/alma-language"):
    if p not in sys.path:
        sys.path.insert(0, p)
