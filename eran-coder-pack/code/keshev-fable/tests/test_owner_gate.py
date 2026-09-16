"""Owner-gate enforcement: drop real speech that isn't Iddo's voice, but never
let a dead gate silence the mic."""
from app.router import Router


class _J:
    def __init__(self): self.events = []
    def event(self, evt, **kw): self.events.append((evt, kw))


class _Spool:
    def __init__(self): self.completed = []
    def complete(self, rid): self.completed.append(rid)


class _Stt:
    class R:
        ok = True; text = "שלום"; avg_logprob = -0.2; lang = "he"; ms = 100
        reason = ""
    def decode(self, rid, wav): return self.R()


class _Typer:
    def __init__(self): self.typed = []
    def deliver(self, rid, text): self.typed.append(text); return True, "ok"
    def enter(self, rid, focus): return True, "ok"


class _ShadowLow:
    def cos(self, wav): return 0.51        # a TV voice, not Iddo


class _ShadowHigh:
    def cos(self, wav): return 0.80        # Iddo


class _ShadowDead:
    def cos(self, wav): return None        # gate down / timeout


def _router(shadow, floor):
    return Router(journal=_J(), spool=_Spool(), stt=_Stt(), typer=_Typer(),
                  read_wav=lambda rid: b"\x00\x00" * 16000,
                  owner_shadow=shadow, owner_floor=floor)


def test_impostor_below_floor_is_blocked():
    r = _router(_ShadowLow(), 0.60)
    assert r.process_one("a") == "owner_blocked"
    assert any(e[0] == "OWNER_BLOCK" for e in r.journal.events)
    assert r.typer.typed == []            # nothing typed


def test_owner_above_floor_types():
    r = _router(_ShadowHigh(), 0.60)
    assert r.process_one("b") == "typed"
    assert r.typer.typed == ["שלום"]


def test_dead_gate_never_silences():
    # a shadow-miss (None) must NOT block — a dead gate can't mute the mic
    r = _router(_ShadowDead(), 0.60)
    assert r.process_one("c") == "typed"
    assert r.typer.typed == ["שלום"]


def test_shadow_only_when_floor_none():
    # floor None = measure, never block, even a low score types
    r = _router(_ShadowLow(), None)
    assert r.process_one("d") == "typed"
    assert r.typer.typed == ["שלום"]
