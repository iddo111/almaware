> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** this GUI is not the canonical brain until the from-scratch learner is connected and verified.

# חוות הנמלים / Ant Farm

> **סטטוס קנוני:** חוות הנמלים היא מעבדת Proto‑Yigael +
> Proto‑Eran + Proto‑Baby‑Cave בתוך `Project Shlomo`.
> המודל `qwen3:4b-instruct` המחובר כרגע הוא **גשר דמו טקסטואלי בלבד**,
> לא המוח של הנמלים ולא ניסוי הלמידה מאפס.

פרויקט מקומי ונפרד מ־Alien Ant Farm AI ומ־Antigravity. אין בו קוד
מהאתר החיצוני Smart Birdfeeder.

המטרה המיידית: לבחור אחת מתשע נמלים, לדבר אליה בעברית ולקבל תשובה
עברית קולית ממודל מקומי קטן. לכל נמלה זהות וזיכרון שיחה משלה. שלושה
בודקים דטרמיניסטיים מציגים אמת, נורמות ובהירות לאחר כל תשובה.

## הפעלה

לחיצה כפולה על:

`D:\CLAUDE\ant-farm\launch_ant_farm.cmd`

או:

```powershell
cd D:\CLAUDE\ant-farm
python server.py --open
```

הכתובת המקומית היא `http://127.0.0.1:8765/`.

## מודל

ברירת המחדל היא `qwen3:4b-instruct` דרך Ollama מקומי. זהו מודל 4B
קטן במצב Instruct, לא תג ה־Thinking בעל השם הדומה:

```powershell
ollama pull qwen3:4b-instruct
python server.py --check
```

אפשר לשנות בלי לערוך קוד:

```powershell
$env:ANT_FARM_MODEL = "qwen3:4b-instruct"
$env:ANT_FARM_OLLAMA_URL = "http://127.0.0.1:11434"
python server.py
```

אין תשובות דמה במצב הרגיל. אם Ollama או המודל אינם זמינים, הממשק מציג
חסימה מפורשת.

## גבול ה־MVP

- קיים: תשע זהויות, זיכרון SQLite, שיחה אמיתית עם small LM, ממשק קולי
  בעברית, קול תשובה, שלושה בודקים וכללי מושבה.
- עדיין לא קיים: אימון משקלים מאפס, הרבה מופעי מודל מקבילים, שפה מתפתחת
  שנמדדה ניסויית, בחירה אבולוציונית ועדכון דורות.
- הבודקים בממשק הם כרגע בדיקות דטרמיניסטיות, לא שלושה מודלי שופט נפרדים.

## בדיקות

```powershell
python -m unittest discover -s tests -v
```

## Persistent startup and recovery

Install the per-user watchdog once:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_ant_farm_autostart.ps1
```

The `ALMAWARE Ant Farm` scheduled task starts after the current Windows user
logs on. The watchdog starts Ollama when necessary, keeps `server.py` running,
and retries after a crash. Logs are written under `data\logs`.

To remove the scheduled task:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_ant_farm_autostart.ps1 -Uninstall
```

This protects against application crashes and normal reboots after user logon.
It cannot operate while the PC is powered off, and this per-user task is not a
Windows system service.
