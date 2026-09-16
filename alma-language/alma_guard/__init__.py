# -*- coding: utf-8 -*-
"""ALMA-GUARD — a neural network woven in ALMA, not a rules engine.

v0.1: text -> sparks -> a weave of knots -> a verdict.

Iddo, 2026-09-11 11:48/11:51:
    "לחזור למודל פרום-סקראץ' בשפת עלמה שלנו - מגן וסורק פרומפט אינג'קשן"
    "זה לא רעיון, זה פרויקט חדש - מודל רשת נוירונים, לא קוד."

Nothing in this package pattern-matches an attack. The feature extractor
(`encoding.py`) holds NO attack vocabulary at all - only character n-grams and
message SHAPE. Every word that ends up meaning "danger" was learned by a cord
thickening, under pain and pleasure (alma/loom.py step 3b).
"""
__version__ = "0.1.0"
