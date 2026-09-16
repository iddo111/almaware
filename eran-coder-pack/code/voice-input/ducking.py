"""ducking.py - duck (lower) the volume of playing media app audio sessions
to a target percentage while Iddo is talking, then restore the prior level.

Uses pycaw (Windows Core Audio / WASAPI per-session volume). We do NOT mute or
kill audio - we remember each session's master volume scalar and set it to
duck_pct%, then put it back exactly where it was.

Sessions belonging to the voice loop itself (python, ffplay, the terminal) are
excluded so ducking never silences our own TTS / Claude Code window.

  python ducking.py list           # show active audio sessions + volumes
  python ducking.py test           # duck to 10% for 3s, then restore

"""
from __future__ import annotations

import logging
import sys
import time

logger = logging.getLogger("voiceinput.ducking")

DEFAULT_EXCLUDE = {"python.exe", "ffplay.exe", "claude.exe",
                   "windowsterminal.exe", "conhost.exe"}

def _sessions():
    from pycaw.pycaw import AudioUtilities
    return AudioUtilities.GetAllSessions()

def list_sessions() -> list[dict]:
    out = []
    for s in _sessions():
        try:
            vol = s.SimpleAudioVolume
            name = (s.Process.name() if s.Process else "system")
            out.append({
                "name": name,
                "pid": (s.Process.pid if s.Process else 0),
                "volume": round(vol.GetMasterVolume(), 3),
                "muted": bool(vol.GetMute()),
            })
        except Exception as e:  # noqa: BLE001
            logger.debug("session read failed: %s", e)
    return out

class Ducker:
    """Remembers prior per-session volumes and restores them. Idempotent:
    calling duck() twice won't 'forget' the original level."""

    def __init__(self, duck_pct: int = 10, exclude: set[str] | None = None,
                 enabled: bool = True):
        self.target = max(0.0, min(1.0, duck_pct / 100.0))
        self.exclude = {e.lower() for e in (exclude or set())} | DEFAULT_EXCLUDE
        self._saved: dict[int, float] = {}   # pid -> original volume scalar
        self._ducked = False
        # Iddo: the mic must NEVER lower other apps' volume. duck_pct>=100 (or
        # enabled=False) makes duck()/restore() complete no-ops.
        self.enabled = bool(enabled) and self.target < 0.999

    def duck(self) -> list[str]:
        """Lower every non-excluded media session to target. Returns the names
        of the sessions actually ducked."""
        if not self.enabled:
            return []
        if self._ducked:
            return []
        ducked = []
        for s in _sessions():
            try:
                name = (s.Process.name() if s.Process else "system")
                if name.lower() in self.exclude:
                    continue
                vol = s.SimpleAudioVolume
                cur = vol.GetMasterVolume()
                # only duck things that are actually audible above the target
                if cur <= self.target + 0.001:
                    continue
                pid = s.Process.pid if s.Process else 0
                self._saved[pid] = cur
                vol.SetMasterVolume(self.target, None)
                ducked.append(f"{name}({cur:.0%}->{self.target:.0%})")
            except Exception as e:  # noqa: BLE001
                logger.debug("duck failed for a session: %s", e)
        self._ducked = bool(ducked) or self._ducked
        if ducked:
            logger.info("ducked: %s", ", ".join(ducked))
        return ducked

    def restore(self) -> None:
        """Put every ducked session back to its remembered volume."""
        if not self._saved:
            self._ducked = False
            return
        live = {}
        for s in _sessions():
            try:
                pid = s.Process.pid if s.Process else 0
                live[pid] = s
            except Exception:  # noqa: BLE001
                pass
        for pid, original in list(self._saved.items()):
            s = live.get(pid)
            if not s:
                continue
            try:
                s.SimpleAudioVolume.SetMasterVolume(original, None)
            except Exception as e:  # noqa: BLE001
                logger.debug("restore failed pid=%s: %s", pid, e)
        logger.info("restored %d session(s)", len(self._saved))
        self._saved.clear()
        self._ducked = False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        for s in list_sessions():
            print(f"  {s['name']:<28} pid={s['pid']:<7} vol={s['volume']:.0%} "
                  f"{'[muted]' if s['muted'] else ''}")
    elif cmd == "test":
        d = Ducker(duck_pct=10)
        print("Sessions BEFORE:")
        for s in list_sessions():
            print(f"  {s['name']:<28} vol={s['volume']:.0%}")
        print("\nDucking to 10% ...")
        print("  ducked:", d.duck())
        print("Sessions DURING (should show ~10%):")
        for s in list_sessions():
            print(f"  {s['name']:<28} vol={s['volume']:.0%}")
        time.sleep(3)
        d.restore()
        print("\nRestored. Sessions AFTER:")
        for s in list_sessions():
            print(f"  {s['name']:<28} vol={s['volume']:.0%}")
