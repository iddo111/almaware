# Qwen3 Coder 480B על DGX1-3

מסלול מבודד עבור `Qwen3-Coder-480B-A35B-Instruct` ב־`Q4_K_M`. הוא אינו מוחק את Grok-1 ואינו משנה את xAI Grok Build CLI במחשב Windows.

## מאפיינים

- מקור: `Qwen/Qwen3-Coder-480B-A35B-Instruct`.
- quant: `unsloth/Qwen3-Coder-480B-A35B-Instruct-GGUF`, תיקיית `Q4_K_M`, שישה shards בלבד.
- גודל צפוי: כ־290GB עשרוני.
- Runtime: עותק llama.cpp הקיים ב־DGX1, עם RPC אל `<fabric-ip>:50052` ו־`<fabric-ip>:50052`.
- Context התחלתי: 32K.
- שמורים הדגלים `--no-cache-prompt` ו־`--no-cache-idle-slots`.

## בטיחות והחלפה

`switch-model.sh qwen` עוצר רק ראש Grok ידני שה־command line שלו כולל את קובץ Grok המדויק. הוא אינו הורג `rpc-server`, אינו משתמש ב־SIGKILL ואינו מוחק מודלים.

`switch-model.sh grok` עוצר את שירות Qwen ומעלה את פקודת Grok שהייתה פעילה לפני ההתקנה.

אין להפעיל את Qwen לפני שכל ששת ה־shards הושלמו ואומתו.

## תוצאה מאומתת — 18.07.2026

- כל ששת ה־shards הושלמו; גודל המודל שה־runtime מדווח: `290052841472` bytes.
- מספר פרמטרים: `480154875392`; context פעיל: `32768`.
- טעינה מלאה על DGX1–3: כ־10 דקות ו־58 שניות.
- health מקומי וחיצוני: PASS.
- מבחן קוד בטוח: פונקציית `clamp` עברה 4/4 בדיקות ב־5.806 שניות.
- מבחן Tailscale נוסף החזיר `def double(x): return x * 2` בתוך 3.06 שניות.
- קצב שנמדד במבחן הראשון: prompt כ־25.03 tok/s; generation כ־8.38 tok/s.
- כתובת: `https://<tailnet-host>:8448/` (Tailnet בלבד).

שירות `qwen3-coder-480b.service` מופעל באתחול. שירות `grok1-preserved.service` נשמר אך מושבת, וה־xAI Grok Build CLI במחשב Windows לא שונה.
