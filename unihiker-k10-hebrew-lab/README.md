# UNIHIKER K10 — מעבדת חושים

דמו ראשון, מקומי ולא־משחקי ל־UNIHIKER K10. הוא מציג על מסך ה־2.8 אינץ' לוח חישה בהיר ובניגודיות גבוהה, בלי חשבון, ענן, Wi‑Fi, Bluetooth, צילום, שמירת מצלמה, הקלטה או כרטיס SD.

הפרויקט נבנה בלבד. הוא **לא הועלה ללוח**, לא פתח יציאה טורית, ולא נגע ב־COM18.

## מה מוצג

- הכותרת העברית **מעבדת חושים**.
- זהות מקומית: `K10`, ארבע הספרות הנמוכות של מזהה ה־eFuse, ו־`OFFLINE`.
- אור סביבתי ב־lux ופס עוצמה לוגריתמי־בקירוב.
- טמפרטורה ב־°C ולחות יחסית מה־AHT20; במקרה של קריאה לא תקינה מוצג `--.-`.
- ערכי X/Y/Z ועוצמה גולמית ממד התאוצה, יחד עם נקודת הטיה.
- מצב כפתורי A ו־B בזמן אמת.

ערכי התאוצה מוצגים בכוונה כערכים גולמיים: ה־API הרשמי מחזיר `int`, אך אינו מתעד יחידת מידה להחזרה הזאת. אין כאן המרה לא־מאומתת ל־g או ל־m/s².

## עברית ו־RTL — מה באמת קורה

ספריית K10 הרשמית מתעדת טקסט סיני ואנגלי, ולא מתעדת עברית או מנוע bidi/RTL. לכן הקוד **אינו שולח UTF‑8 עברי אל `canvasText`** ואינו טוען שתמיכת עברית קיימת.

שבעה ביטמפים חד־צבעיים נוצרו מראש בסדר חזותי RTL מ־Noto Sans Hebrew Bold 3.001. בזמן ריצה הם מצוירים כרצפים אופקיים של פיקסלים באמצעות פרימיטיבי ה־Canvas הרשמיים. כך הכותרת והתוויות `זהות`, `אור`, `טמפ`, `לחות`, `תאוצה` ו־`כפתורים` אינן תלויות בפונט המובנה. קובץ המקור הוא [`include/hebrew_bitmaps.h`](include/hebrew_bitmaps.h).

פונט המקור המקומי ששימש לרסטריזציה:

- `NotoSansHebrew-Bold.ttf`, Version 3.001
- SHA-256: `96F88305D31A8432F0FE6648C853CB9EF77DB8E52ADA8948ED0C577037D45423`
- הפונט עצמו **אינו כלול** בפרויקט; ראו [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## בנייה בלבד

נדרש PlatformIO Core 6.x ו־Git. הבנייה הראשונה מורידה את ה־SDK הרשמי של DFRobot; תוכנת הלוח עצמה נשארת מקומית ואינה משתמשת ברשת.

```powershell
Set-Location D:\CLAUDE\unihiker-k10-hebrew-lab
$env:PYTHONUTF8 = '1'
pio run -e unihiker_k10_compile_only
```

ה־environment כולל guard מכוון:

```ini
upload_port = COMPILE_ONLY_DO_NOT_UPLOAD
monitor_port = COMPILE_ONLY_DO_NOT_OPEN
```

לכן פקודת הבנייה הרגילה אינה בוחרת או פותחת COM כלשהו.

### בדיקות מארח

הבדיקות מקמפלות ומריצות את הלוגיקה הטהורה (תזמון כולל wraparound, תחומי AHT20, סולם אור, מיפוי תאוצה ושלמות ביטמפי העברית), ואז בודקות סטטית שמקור ה־firmware אינו כולל API של רשת, מצלמה, שמירה, הקלטה או משחק.

```powershell
Set-Location D:\CLAUDE\unihiker-k10-hebrew-lab
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\run_host_tests.ps1
```

הסקריפט מחפש `g++` ב־PATH, וב־Windows משתמש גם ב־`C:\msys64\usr\bin\g++.exe` אם הוא קיים.

## תוצאת הבנייה המאומתת

הסעיף הזה מתעדכן רק אחרי build אמיתי; הוא אינו הוכחת חומרה ולא הוכחת תצוגה פיזית.

- PlatformIO build: `PENDING`
- Firmware artifact: `PENDING`
- SHA-256: `PENDING`
- Host tests: `PENDING`
- Upload/serial/hardware display test: **לא בוצעו**

## גיבוי, העלאה ושחזור — לעתיד בלבד

הפקודות הבאות הן נוהל ידני עתידי, **לא בוצעו בסשן הזה**. הן יפתחו את היציאה שתבחרו ועלולות לאפס את הלוח. אין להריץ אותן עד שמזהים מחדש את ה־K10, סוגרים Serial Monitor, מסירים ספקי כוח כפולים ומחליטים במפורש להחליף את הקושחה.

### 1. זיהוי והכנת שם יציאה

בחרו את היציאה לאחר זיהוי טרי; אל תעתיקו מספר COM היסטורי:

```powershell
$K10_PORT = '<VERIFIED_K10_PORT>'
```

אם `get-security-info` מדווח Secure Boot או Flash Encryption פעילים, עצרו וכתבו נוהל מותאם לפני כל כתיבה:

```powershell
pio pkg exec -p tool-esptoolpy -c "esptool --chip esp32s3 --port $K10_PORT get-security-info"
```

### 2. גיבוי מלא לפני כתיבה

מפרט K10 הרשמי מציין 16 MB Flash. `ALL` מבקש מ־esptool לזהות את הגודל, ואז הבדיקה המקומית דורשת בדיוק 16,777,216 בתים.

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDir = Join-Path $PWD "backups\$stamp"
New-Item -ItemType Directory -Path $backupDir | Out-Null
$backupFile = Join-Path $backupDir 'k10-full-flash-before-demo.bin'

pio pkg exec -p tool-esptoolpy -c "esptool --chip esp32s3 --port $K10_PORT --baud 460800 read-flash 0 ALL `"$backupFile`""

if ((Get-Item -LiteralPath $backupFile).Length -ne 16777216) {
    throw 'Unexpected backup size; do not flash.'
}
Get-FileHash -LiteralPath $backupFile -Algorithm SHA256
```

שמרו את קובץ הגיבוי ואת ה־SHA-256 במקום פרטי נוסף. dump מלא עלול להכיל הגדרות, מזהים או סודות שהיו בקושחה הקודמת.

### 3. העלאה מפורשת בלבד

בנו שוב, בדקו שה־artifact וה־hash הם אלה שהתכוונתם אליהם, ורק אז דרסו במפורש את guard היציאה:

```powershell
pio run -e unihiker_k10_compile_only
Get-FileHash -LiteralPath .\.pio\build\unihiker_k10_compile_only\firmware.bin -Algorithm SHA256
pio run -e unihiker_k10_compile_only -t upload --upload-port $K10_PORT
```

אין להשתמש ב־`erase-flash`; אין צורך למחוק את כל ה־Flash כדי להעלות את הדמו.

### 4. שחזור מלא של הגיבוי

ודאו ש־`$backupFile` הוא הקובץ המקורי ושה־hash שלו תואם לרישום ששמרתם:

```powershell
Get-FileHash -LiteralPath $backupFile -Algorithm SHA256
pio pkg exec -p tool-esptoolpy -c "esptool --chip esp32s3 --port $K10_PORT --baud 460800 write-flash 0 `"$backupFile`""
pio pkg exec -p tool-esptoolpy -c "esptool --chip esp32s3 --port $K10_PORT --baud 460800 verify-flash 0 `"$backupFile`""
```

השחזור הוא כתיבה הרסנית ביחס לקושחה הנוכחית, אך מחזיר את תמונת ה־Flash הגולמית שנשמרה. אם בדיקת ה־hash, הגודל, מצב האבטחה או זהות הלוח אינם ודאיים — לא כותבים.

## מבנה

- `platformio.ini` — לוח K10 וגרסאות SDK רשמיות נעולות ל־commit.
- `src/main.cpp` — אתחול K10, דגימת חיישנים ותצוגת הדשבורד.
- `include/dashboard_logic.h` — לוגיקה טהורה וניתנת לבדיקה במארח.
- `include/hebrew_bitmaps.h` — עברית RTL כרשתות 1-bit.
- `tests/` — בדיקות C++ ובדיקת מדיניות offline/non-game.

## מקורות ראשוניים

- [מדריך PlatformIO הרשמי של UNIHIKER K10](https://www.unihiker.com/wiki/K10/GettingStarted/gettingstarted_platformio/) — מגדיר `platform-unihiker`, לוח `unihiker_k10` ו־build flags.
- [רשימת Arduino/PlatformIO API הרשמית](https://www.unihiker.com/wiki/K10/CodeReference/CodeReference_arduinoide/) — `readALS`, תאוצה, כפתורים, AHT20 ו־Canvas.
- [מפרט החומרה הרשמי](https://www.unihiker.com/wiki/K10/HardwareReference/hardwarereference_specs/) — ESP32-S3 N16R8, מסך 240×320, AHT20, LTR303ALS, SC7A20H וכפתורי A/B.
- [DFRobot platform-unihiker, commit 508e318](https://github.com/DFRobot/platform-unihiker/commit/508e31875ad92205bf946e28570fb78fc01ceb2e).
- [DFRobot framework-arduinounihiker, commit 9fabfd6](https://github.com/DFRobot/framework-arduinounihiker/commit/9fabfd6d6324dbb304ad47947675baf7cf1ab29e).
- [ספריית DFRobot_AHT20 הרשמית](https://github.com/DFRobot/DFRobot_AHT20).
- [תיעוד esptool הרשמי ל־ESP32-S3](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/esptool/basic-commands.html) — `read-flash`, `write-flash` ו־`verify-flash`.
- [Noto Hebrew הרשמי](https://github.com/notofonts/hebrew) — מקור פונט ה־OFL ששימש לרסטריזציה בלבד.

## גבולות האימות

Build מוצלח מאמת התאמת source/toolchain/linker בלבד. בלי העלאה ובדיקה פיזית אי אפשר לאשר את כיוון המסך בפועל, חדות הביטמפים על הפאנל המסוים, תקינות החיישנים, כיול, טמפרטורה עצמית של הלוח או חיווט/חשמל. המצלמה והאחסון אינם מאותחלים בקוד הדמו.

