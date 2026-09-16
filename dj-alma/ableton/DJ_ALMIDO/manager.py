# -*- coding: utf-8 -*-
"""manager.py -- the Live Remote Script itself: a ControlSurface subclass
that owns a non-blocking TCP/JSON socket server (server.py) and polls it
once per tick, dispatching each command through dispatch.py.

THE SCHEDULER MECHANISM, confirmed not guessed (see __init__.py's docstring
for the sources): `ControlSurface.schedule_message(self, delay_in_ticks,
callback, parameter=None)`, defined in
ableton/v2/control_surface/control_surface.py (this exact Live 12.4.5
install's own copy). A "tick" is Live's own internal ~100ms scheduling
granularity -- this is the SAME mechanism ideoforms/AbletonOSC uses for its
socket server (`self.schedule_message(0, self.tick)` in __init__, then
`tick()` calls `self.schedule_message(1, self.tick)` at the end of itself to
re-arm). This file follows that pattern exactly. There is no separate
"update_display" hook used here -- schedule_message is the real, current
mechanism for this Live version, not update_display (an older idiom from a
different/earlier framework generation).

This module is the ONLY file in this package that imports `Live` or
`ableton.v2.control_surface` -- both exist only inside Live's embedded
interpreter. dispatch.py and server.py stay pure-stdlib so they can be unit
tested from a normal host Python with no Ableton running (see ../tests/).
"""
import json
import os
import time

from ableton.v2.control_surface import ControlSurface
import Live

from .server import TCPJSONServer
from .dispatch import DispatchState, dispatch

HOST = "127.0.0.1"
PORT = 8865  # claimed in RAMCHAT 2026-09-08 11:0x (claude-cli-FABLE-dj) -- does
             # NOT collide with the booth server's :8863, which stays untouched.

# Absolute, not relative to this file: this package gets COPIED into
# ...\Documents\Ableton\User Library\Remote Scripts\DJ_ALMIDO\ (see
# ../INSTALL.md); D:\CLAUDE\dj-alma stays put.
LOG_PATH = r"D:\CLAUDE\dj-alma\ableton\log.jsonl"


class Manager(ControlSurface):
    def __init__(self, c_instance):
        super(Manager, self).__init__(c_instance)
        self._server = None
        self._state = None
        try:
            self._state = DispatchState(song=self.song, live_module=Live, log_fn=self._log_dispatch)
            self._server = TCPJSONServer(HOST, PORT, self._on_message, logger=self._log_status)
            self.schedule_message(0, self._tick)
            self.show_message("DJ_ALMIDO: listening on %s:%d" % (HOST, PORT))
            self._log_status("DJ_ALMIDO started, listening on %s:%d" % (HOST, PORT))
        except OSError as e:
            # Most likely cause: the port is already bound (e.g. this script
            # got re-enabled without Live fully releasing the old socket).
            # Fails LOUDLY via show_message (visible in Live's own status
            # bar) rather than leaving Iddo with a silently-dead control
            # surface -- Broken Windows Law.
            self.show_message("DJ_ALMIDO: could not bind %s:%d (%s)" % (HOST, PORT, e))
            self._log_status("DJ_ALMIDO FAILED to start: %r" % (e,))

    # -- the tick loop --------------------------------------------------
    def _tick(self):
        if self._server is not None:
            self._server.process()
        self.schedule_message(1, self._tick)

    def _on_message(self, msg):
        return dispatch(self._state, msg)

    # -- logging: every command + every connection event, one file -------
    def _log_status(self, text):
        self._append_log({"ts": time.time(), "type": "status", "text": text})

    def _log_dispatch(self, text):
        self._append_log({"ts": time.time(), "type": "dispatch", "text": text})

    def _append_log(self, record):
        try:
            os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except OSError:
            pass  # a full disk / locked file must never crash the DJ session

    def disconnect(self):
        if self._server is not None:
            self._server.shutdown()
        self._log_status("DJ_ALMIDO disconnected")
        super(Manager, self).disconnect()
