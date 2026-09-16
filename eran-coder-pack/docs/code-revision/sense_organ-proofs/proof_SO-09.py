# -*- coding: utf-8 -*-
"""PROOF SO-09 -- the organ bound 0.0.0.0 with no auth: any LAN or Tailscale host could
drive ERAN's mouth and ear. Its own docstring says the senses live on eran2 because of the
eran1<->eran2 fabric, and the only client (babble.py) dials <fabric-ip>.

    python3 proof_SO-09.py ~/eran-organs/sense_organ.py.bak-rev-20260906   -> FAIL
    python3 proof_SO-09.py ~/eran-organs/sense_organ.py                    -> PASS

Reads a default. Binds nothing.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _proof_harness as H                                          # noqa: E402

PATH = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/eran-organs/sense_organ.py")
print("PROOF SO-09 against %s" % PATH)
checks = []

d = H.load(PATH, env={"ERAN_ORGAN_HOST": None, "ERAN_ORGAN_PORT": None})
checks.append(("default bind is the fabric address, not the whole world",
               d.HOST == "<fabric-ip>", "HOST=%r PORT=%r" % (d.HOST, d.PORT)))
checks.append(("default is not 0.0.0.0", d.HOST != "0.0.0.0", "HOST=%r" % d.HOST))

o = H.load(PATH, env={"ERAN_ORGAN_HOST": "127.0.0.1"})
checks.append(("a local test can still override the host",
               o.HOST == "127.0.0.1", "HOST=%r" % o.HOST))

u = os.path.expanduser("~/.config/systemd/user/eran-senses.service")
txt = open(u).read() if os.path.exists(u) else ""
checks.append(("the unit states the bind address as visible configuration",
               "Environment=ERAN_ORGAN_HOST=<fabric-ip>" in txt,
               "%s: %s" % (u, "Environment=ERAN_ORGAN_HOST present" if
                           "ERAN_ORGAN_HOST" in txt else "no ERAN_ORGAN_HOST line")))

H.report(checks)
