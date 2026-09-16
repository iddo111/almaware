"""alma-mic / app.py — headless dictation (no window): the one pipeline, capture->VAD->STT->type.

Run:  python app.py        (types into the focused window if config.type_output is on)
Settings live in config.json (edit there or via the GUI's ⚙ panel).
"""
from __future__ import annotations
import sys
import time

from config import Config
from pipeline import Pipeline


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    cfg = Config.load()
    p = Pipeline(
        cfg,
        on_text=lambda t, l: print(f"[{l}] {t}", flush=True),
        on_device=lambda d: print(f"mic: {d}", flush=True),
        on_model=lambda d: print(f"model: {d}", flush=True),
        on_error=lambda m: print(f"error: {m}", flush=True),
        on_log=lambda m: print(m, flush=True),
    )
    p.start()
    print(f"alma-mic running (type_output={cfg.type_output}). Speak. Ctrl+C to stop.",
          flush=True)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        p.stop()
        print("stopped.", flush=True)


if __name__ == "__main__":
    main()
