"""Adversarial review round: feed each K2 safety module to a DIFFERENT
worker with one mission — find the guard that cannot fire."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fleet  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "harness" / "adversarial"
OUT.mkdir(exist_ok=True)

MISSION = """You are an adversarial reviewer for a Windows dictation app. The repo's
worst historical bug class is THE GUARD THAT CANNOT FIRE: written, wired, tested,
and structurally unable to act (examples that shipped: a logprob floor below the
entire measured distribution; a tray alarm with no drawing backend; a VAD placed
after the client had already removed everything it guarded against; an audit verdict
the decision never consulted; a hotkey parser with no RegisterHotKey call).

Read the module below. Report AT MOST your 3 strongest findings, ranked. For each:
FINDING: <one line>
WHY IT CANNOT FIRE / WHEN IT LIES: <2-4 lines, concrete — name the exact line/function>
FIX: <one line>
If you find no dead guard, say so and instead name the single riskiest assumption.
Do not restate the module's documentation back at me. Concrete or silent.

MODULE:
"""

JOBS = {
    "interlock-gpt-oss-120b": ("gpt-oss-120b", "k2/interlock.py"),
    "typer-glm-4.7-flash": ("glm-4.7-flash", "k2/typer.py"),
    "presence-nemotron-3-super": ("nemotron-3-super", "k2/presence.py"),
    "sttclient-qwen3-coder-next-fp8": ("qwen3-coder-next-fp8",
                                       "k2/sttclient.py"),
}


def main() -> None:
    for name, (model, relpath) in JOBS.items():
        src = (REPO / relpath).read_text(encoding="utf-8")
        print(f"--- adversarial {name}")
        try:
            text = fleet.ask(model, MISSION + src, max_tokens=1200,
                             timeout=600)
        except Exception as exc:  # noqa: BLE001
            text = f"WORKER-DOWN {type(exc).__name__}: {exc}"
        (OUT / f"{name}.md").write_text(text, encoding="utf-8")
        print(f"    {len(text)} chars")


if __name__ == "__main__":
    main()
