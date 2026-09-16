# bochen1.py — הבוחן השקט של שיעור 1. מריצים: python bochen1.py
# בודק את yoman.py של עידו בלי רחמים וברוך. לא נוגע בקוד שלו — רק שופט.
import importlib.util
import os
import sys

TOV = "✅"
RA = "❌"
nekudot = 0


def bdok(shem, tnai, esa):
    global nekudot
    if tnai:
        print(f"{TOV} {shem}")
        nekudot += 1
    else:
        print(f"{RA} {shem} — {esa}")


print("=" * 46)
print("   הבוחן השקט — שיעור 1: היומן")
print("=" * 46)

# 1. הקובץ קיים
kayam = os.path.exists("yoman.py")
bdok("yoman.py קיים", kayam, "שמור את הקובץ בתיקייה הזו בדיוק בשם yoman.py")
if not kayam:
    sys.exit(1)

# 2. הקוד נטען בלי שגיאות (מריץ אותו!)
if os.path.exists("yoman.txt"):
    os.remove("yoman.txt")           # דף חלק לכל ריצת בוחן
try:
    spec = importlib.util.spec_from_file_location("yoman", "yoman.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    bdok("הקוד רץ בלי שגיאות", True, "")
except Exception as e:
    bdok("הקוד רץ בלי שגיאות", False, f"{type(e).__name__}: {e}")
    sys.exit(1)

# 3. שתי הפונקציות קיימות
bdok("יש פונקציה ktov_shura", hasattr(mod, "ktov_shura"),
     "def ktov_shura(kovetz, hodaa):")
bdok("יש פונקציה kra_hakol", hasattr(mod, "kra_hakol"),
     "def kra_hakol(kovetz):")

# 4. היומן באמת נכתב
nichtav = os.path.exists("yoman.txt")
bdok("yoman.txt נוצר", nichtav, "הקריאות ל-ktov_shura לא כתבו קובץ")

# 5. יש בו לפחות 2 שורות ובכל שורה יש ' | '
if nichtav:
    with open("yoman.txt", encoding="utf-8") as f:
        shurot = f.readlines()
    bdok("יש לפחות 2 שורות", len(shurot) >= 2, f"נמצאו {len(shurot)}")
    bdok("כל שורה בפורמט zman | hodaa",
         all(" | " in s for s in shurot),
         "חסר ' | ' באחת השורות")

# 6. אתגר הזהב (רשות)
if hasattr(mod, "sfor_milim"):
    try:
        n = mod.sfor_milim("yoman.txt")
        print(f"\U0001F3C6 אתגר הזהב: sfor_milim החזירה {n} — כבוד!")
    except Exception as e:
        print(f"\U0001F949 אתגר הזהב נוסה אבל נפל: {e}")

print("-" * 46)
if nekudot >= 6:
    print("\U0001F389 עברת! כתוב לפייבל: 'עברתי שיעור 1'")
    print("   30 שנה חיכו — ולקח לך ערב אחד לחזור.")
else:
    print(f"עוד לא ({nekudot}/6) — תקן לפי ההערות והרץ שוב. זה חלק מהעניין.")
