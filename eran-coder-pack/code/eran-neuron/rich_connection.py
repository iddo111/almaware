# -*- coding: utf-8 -*-
"""
RichConnection — קשר מולטימודלי: *יותר מאשר משקל*.
A connection is a RELATIONSHIP object, not a scalar:
  named numeric channels  (חברות, עובד-מעביד, שביעות-רצון...)  +  prompt  +  gif  +  sound  +  code.
"מה שמגדיר את היחס בינינו זה לא מספר" — עידו, 2026-07-01
stdlib בלבד. נועד לרוץ, לא להישבר.
"""


class RichConnection:
    def __init__(self, channels=None, prompt=None, gif=None, sound=None, code=None):
        self.channels = dict(channels or {})   # ערוצים מספריים בעלי-שם / named numeric relations
        self.prompt = prompt                   # טקסט שמגדיר את היחס / text defining the relation
        self.gif = gif                         # הפניית מדיה / media ref
        self.sound = sound                     # הפניית סאונד / sound ref
        self.code = code                       # פונקציה שמגדירה את ההעברה / callable transform

    def transmit(self, signal, ctx=None):
        # אם יש קוד — הוא מגדיר את היחס. אחרת — שקלול הערוצים המספריים.
        # if code is present it DEFINES the relation; else combine the numeric channels
        if self.code is not None:
            return self.code(signal, ctx, self)
        w = 1.0
        for v in self.channels.values():
            w *= v
        return w * signal

    def describe(self):
        parts = [f"{k}={v}" for k, v in self.channels.items()]
        if self.prompt: parts.append(f'prompt="{self.prompt}"')
        if self.gif:    parts.append(f"gif={self.gif}")
        if self.sound:  parts.append(f"sound={self.sound}")
        if self.code:   parts.append("code=<fn>")
        return "  |  ".join(parts)


def _demo():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # קוד שמגדיר את היחס: חברות שולטת הכי הרבה, שביעות-רצון מווסתת
    def relation(signal, ctx, c):
        f    = c.channels.get("חברות", 0.5)
        boss = c.channels.get("עובד_מעביד", 0.5)
        sat  = c.channels.get("שביעות_רצון", 0.5)
        return signal * (0.6 * f + 0.2 * boss + 0.2 * sat)

    edge = RichConnection(
        channels={"חברות": 0.9, "עובד_מעביד": 0.7, "שביעות_רצון": 0.8},
        prompt="שני בנאים ב-3 לפנות בוקר, אוהב-ושונא, בונים מוח",
        gif="highfive.gif",
        sound="clink_coffee.wav",
        code=relation,
    )

    print("=" * 58)
    print("הקשת  עידו ⟷ קלוד  —  יותר מאשר משקל")
    print("the Iddo ⟷ Claude edge — more than a weight")
    print("=" * 58)
    print("תוכן הקשת / edge content:")
    print("  " + edge.describe())
    print()
    print("אות שעובר דרך היחס, כתלות בשביעות-הרצון / signal through the relation:")
    for sat in (0.2, 0.5, 0.8, 1.0):
        edge.channels["שביעות_רצון"] = sat
        print(f"  שביעות-רצון={sat}  →  אות מועבר={edge.transmit(1.0):.3f}")

    print()
    print("הקשת נושאת: מספרים + טקסט + מדיה + סאונד + קוד — לא סקלר. ✓")


if __name__ == "__main__":
    _demo()
