# -*- coding: utf-8 -*-
"""CODER-08 -- a unit file that claims a protection it does not have.

`StartLimitIntervalSec=0` sits in [Service], where systemd ignores it:

  coder-train.service:34: Unknown key name StartLimitIntervalSec in section
  Service, ignoring        (5 occurrences in journalctl --user -u coder-train)

so the unit still carries the default 5 starts / 10 s while its own comment says
"No start-rate limit ... which is the one thing 'never stops' cannot tolerate".
No live harm today, because RestartSec=60 makes five starts in ten seconds
impossible -- but a file that documents a guard it does not have is worse than
one that documents nothing, because the next person reads the comment.

The same drop-in carries CODER-02's RestartPreventExitStatus, so this proof
checks both: the rate limit is where systemd reads it, and the exit-code contract
exists at the unit level.

Run:  python proof_CODER-08.py ../orig    -> FAIL
      python proof_CODER-08.py ../new     -> PASS
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _proofkit import Proof, target_from_argv  # noqa: E402

d = target_from_argv("new")
p = Proof("CODER-08", d)


def parse_units(paths):
    """Effective config: base unit then drop-ins, in name order. -> {section: {k: v}}"""
    cfg = {}
    for path in paths:
        section = None
        for raw in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
                continue
            if "=" in line and section:
                k, v = line.split("=", 1)
                cfg.setdefault(section, {})[k.strip()] = v.strip()
    return cfg


files = []
base = d / "coder-train.service"
if base.exists():
    files.append(base)
dropdir = d / "coder-train.service.d"
if dropdir.is_dir():
    files += sorted(dropdir.glob("*.conf"))
print("  unit files considered: %s" % ([f.name for f in files] or "NONE"))

if not files:
    p.fail("a unit file is present", "nothing to check")
    p.done()

cfg = parse_units(files)
unit = cfg.get("Unit", {})
svc = cfg.get("Service", {})

where = [s for s in ("Unit", "Service") if "StartLimitIntervalSec" in cfg.get(s, {})]
p.check("StartLimitIntervalSec" in unit,
        "StartLimitIntervalSec is in [Unit], where systemd reads it",
        "effective sections: %s -- in [Service] alone it is silently dropped "
        "(journal: 'Unknown key name ... ignoring') and the default 5 starts / "
        "10 s still applies" % (where or ["nowhere"],))

rpes = svc.get("RestartPreventExitStatus", "")
codes = set(rpes.replace(",", " ").split())
p.check("3" in codes,
        "exit 3 (non-finite loss/grad) is not auto-restarted",
        "RestartPreventExitStatus=%r -- train.py: 'exit code 3 means investigate'; "
        "the data order is a pure function of (seed, step) so the NaN returns on "
        "every resume" % (rpes,))
p.check("5" in codes,
        "exit 5 (hold-out leak) is not auto-restarted",
        "README says 'never' for this one")
p.check("1" in codes, "exit 1 (config error) is not auto-restarted")
p.check("4" not in codes,
        "exit 4 (CUDA OOM) IS still restartable",
        "an OOM can clear when the other job on this GPU finishes")

p.check(svc.get("Restart") in ("on-failure", "always"),
        "the unit still restarts real failures", repr(svc.get("Restart")))

p.done()
