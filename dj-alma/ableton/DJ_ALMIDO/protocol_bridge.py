# -*- coding: utf-8 -*-
"""protocol_bridge.py -- imports D:\\CLAUDE\\dj-alma\\bridge\\protocol.py BY
ABSOLUTE PATH, so this package reuses the ONE existing command schema instead
of inventing a second one.

WHY BY PATH, NOT A NORMAL PACKAGE IMPORT: this DJ_ALMIDO/ folder gets COPIED
(see ../INSTALL.md) into
    C:\\Users\\iddo1\\Documents\\Ableton\\User Library\\Remote Scripts\\DJ_ALMIDO\\
which is a different directory from D:\\CLAUDE\\dj-alma\\bridge\\ -- a plain
`import protocol` would only work by accident (if bridge/ happened to be on
sys.path already, which it is not inside Live's embedded interpreter). So
this module finds bridge/protocol.py at its real, fixed location on disk and
loads it explicitly with importlib, independent of where DJ_ALMIDO itself was
copied to.

protocol.py is safe to import into Live's embedded Python 3.11 interpreter:
it is pure stdlib with NO imports at all (verified by reading it) -- no mido,
no dataclasses, nothing that would need packages Live's interpreter lacks.
grammar.py (which DOES use `dataclass` and PEP 604 `X | None` unions) is
deliberately NOT imported here -- that stays on the PC side, in
voice_to_live.py, which runs under the normal host Python.

If bridge/protocol.py cannot be found or fails to import (e.g. Iddo moves
D:\\CLAUDE\\dj-alma), this raises loudly at Manager.__init__ time and the
error goes to Live's log + this package's own log.jsonl -- it must never
silently fall back to a re-typed copy of the command table, because a copy
is exactly the drift bridge/protocol.py's own docstring says smoke_test.py
exists to prevent.
"""
import importlib.util
import os

# The one real location. Not relative to this file (this file gets copied
# elsewhere); a fixed absolute path into the dj-alma repo, which is not
# copied anywhere -- it stays at D:\CLAUDE\dj-alma.
BRIDGE_PROTOCOL_PATH = r"D:\CLAUDE\dj-alma\bridge\protocol.py"


def _load_protocol():
    if not os.path.exists(BRIDGE_PROTOCOL_PATH):
        raise ImportError(
            f"DJ_ALMIDO: cannot find the shared command schema at "
            f"{BRIDGE_PROTOCOL_PATH!r}. This file must exist and be reachable "
            f"from Live's process for DJ_ALMIDO to speak the same commands as "
            f"the Mixcraft bridge (bridge/dj_alma_control.js)."
        )
    spec = importlib.util.spec_from_file_location("dj_alma_bridge_protocol", BRIDGE_PROTOCOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


protocol = _load_protocol()
