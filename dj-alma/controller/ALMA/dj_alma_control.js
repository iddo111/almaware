// dj_alma_control.js -- ALMA psytrance DJ bridge, Mixcraft 10 Controller Script side.
//
// Receives ALMA DJ commands from the Python bridge (bridge/dj_bridge.py via
// bridge/midi_out.py) over a virtual MIDI port (loopMIDI or equivalent --
// see D:\CLAUDE\dj-alma\README.md for setup) and calls the matching
// Mixcraft/Track/Perform API function.
//
// WIRE FORMAT -- KEEP THIS FILE'S COMMANDS TABLE IN SYNC WITH
// bridge/protocol.py BY HAND. There is no way to share code between this
// sandbox and Python (see docs/getting-started/javascript-limitations.md --
// no import/require). smoke_test.py parses both files and diffs the tables
// so drift is caught, not trusted to memory.
//   One command = one MIDI NOTE_ON immediately followed by NOTE_OFF, on
//   CHANNEL (below). note number (value1) = command id. velocity (value2)
//   = one parameter byte, 0-127, meaning is command-specific (see table).
//
// LANGUAGE NOTE: the Mixcraft 10 script VM only documents this keyword set:
//   var if else do while for break continue null undefined function return
//   true false new typeof
// No switch/case, no try/catch, no let/const, no classes, no arrow
// functions, no template literals are documented as available -- so this
// file avoids all of them deliberately, not by oversight. Dispatch is a
// plain if/else-if chain. Never assume Array.prototype helpers (forEach,
// includes, etc.) exist beyond what plain for-loops need.
//
// STATUS (2026-09-04): Mixcraft was NOT found installed anywhere on the PC
// this was written on (checked Program Files, ProgramData, registry,
// AppData, Start Menu, file associations -- all empty) and no virtual MIDI
// port exists yet either. This script has therefore NEVER been loaded by a
// running Mixcraft and its Compile/Reload button has never been clicked --
// see the status report for exactly what is and is not verified. Written
// strictly from the API docs at
// https://github.com/acousticainc/controller-script-api-docs (pulled and
// read in full, not the landing page).

Globals.SetDebug(true); // comment this out once installed for real -- see setting-up.md

// ---- wire format constants (mirror bridge/protocol.py) --------------------
var CHANNEL = 0x0F; // MIDI channel 16, 0-based (OnMIDI convention)

// command id -> name, exactly mirroring bridge/protocol.py's COMMANDS table
var CMD_PLAY = 1;
var CMD_STOP = 2;
var CMD_RECORD_TOGGLE = 3;
var CMD_SET_TEMPO = 4;
var CMD_TEMPO_NUDGE_UP = 5;
var CMD_TEMPO_NUDGE_DOWN = 6;

var CMD_BASS_VOL = 10;
var CMD_BASS_MUTE_TOGGLE = 11;
var CMD_LEAD_VOL = 12;
var CMD_LEAD_MUTE_TOGGLE = 13;
var CMD_DRUMS_VOL = 14;
var CMD_DRUMS_MUTE_TOGGLE = 15;
var CMD_FX_VOL = 16;
var CMD_FX_MUTE_TOGGLE = 17;
var CMD_MASTER_VOL = 18;

var CMD_SECTION_INTRO = 20;
var CMD_SECTION_BUILD = 21;
var CMD_SECTION_DROP = 22;
var CMD_SECTION_BREAK = 23;
var CMD_SECTION_OUTRO = 24;
var CMD_EXTEND_SECTION = 25;
var CMD_STOP_ALL_CLIPS = 26;

// ---- BPM mapping, mirrors bridge/protocol.py bpm_to_param()/param_to_bpm() ---
var TEMPO_MIN_BPM = 120.0;
var TEMPO_MAX_BPM = 160.0;

function ParamToBpm(param) {
  var frac = param / 127.0;
  return TEMPO_MIN_BPM + frac * (TEMPO_MAX_BPM - TEMPO_MIN_BPM);
}

// ---- volume nudge, mirrors bridge/protocol.py NUDGE_UNIT_FRACTION ----------
var NUDGE_UNIT_FRACTION = 0.08; // fraction of full 0..1.0 track volume per 16 units of |param-64|

function ApplyNudge(trackIndex, param) {
  var current = Track.GetVolume(trackIndex);
  var steps = (param - 64) / 16.0; // matches protocol.nudge_param()'s 16-unit step
  var delta = steps * NUDGE_UNIT_FRACTION;
  var next = current + delta;
  if (next < 0.0) { next = 0.0; }
  if (next > 1.0) { next = 1.0; }
  Track.SetVolume(trackIndex, next);
  Globals.Log("nudge track " + trackIndex + " vol " + current + " -> " + next);
}

// ---- track/section layout -- PLACEHOLDERS, edit to match Iddo's real project
// Mirrors bridge/protocol.py STEM_TRACK_INDEX / SECTION_COLUMN. Both files
// must be edited together if the real project layout differs.
var TRACK_BASS = 0;
var TRACK_LEAD = 1;
var TRACK_DRUMS = 2;
var TRACK_FX = 3;

var COL_INTRO = 0;
var COL_BUILD = 1;
var COL_DROP = 2;
var COL_BREAK = 3;
var COL_OUTRO = 4;

// ---- lifecycle functions Mixcraft calls -----------------------------------

function OnStartup() {
  Globals.Log("ALMA DJ control script started. Channel " + (CHANNEL + 1) +
              ", waiting for commands from dj_bridge.py.");
}

function OnShutdown() {
  Globals.Log("ALMA DJ control script shutting down.");
}

function Notify(notificationType, data1, data2) {
  // No hardware LEDs/motorized faders on this control surface (it's a
  // software bridge, not physical hardware) -- feedback is optional. Logged
  // for now so state changes made from Mixcraft's own UI are visible while
  // debugging the mapping.
  Globals.Log("Notify type=" + notificationType + " data1=" + data1 + " data2=" + data2);
}

function OnMIDI(messageType, midiChannel, value1, value2) {
  if (midiChannel != CHANNEL) {
    return; // not our reserved channel -- ignore, never guess
  }
  if (messageType != MIDI.NOTE_ON) {
    return; // we only act on NOTE_ON; NOTE_OFF (value2=0 half of the pair) is a no-op
  }

  var cmd = value1;
  var param = value2;

  if (cmd == CMD_PLAY) {
    Mixcraft.Play();
    Globals.Log("PLAY");
  } else if (cmd == CMD_STOP) {
    if (Mixcraft.IsPlaying()) {
      Mixcraft.TogglePlay();
    }
    Globals.Log("STOP");
  } else if (cmd == CMD_RECORD_TOGGLE) {
    Mixcraft.Record();
    Globals.Log("RECORD_TOGGLE");
  } else if (cmd == CMD_SET_TEMPO) {
    var bpm = ParamToBpm(param);
    Mixcraft.SetTempo(bpm);
    Globals.Log("SET_TEMPO -> " + bpm);
  } else if (cmd == CMD_TEMPO_NUDGE_UP) {
    var stepsUp = param > 0 ? param : 1;
    Mixcraft.SetTempo(Mixcraft.GetTempo() + stepsUp * 0.5);
    Globals.Log("TEMPO_NUDGE_UP " + stepsUp + " steps -> " + Mixcraft.GetTempo());
  } else if (cmd == CMD_TEMPO_NUDGE_DOWN) {
    var stepsDown = param > 0 ? param : 1;
    Mixcraft.SetTempo(Mixcraft.GetTempo() - stepsDown * 0.5);
    Globals.Log("TEMPO_NUDGE_DOWN " + stepsDown + " steps -> " + Mixcraft.GetTempo());

  } else if (cmd == CMD_BASS_VOL) {
    ApplyNudge(TRACK_BASS, param);
  } else if (cmd == CMD_BASS_MUTE_TOGGLE) {
    Track.Mute(TRACK_BASS, !Track.IsMuted(TRACK_BASS));
    Globals.Log("BASS_MUTE_TOGGLE -> " + Track.IsMuted(TRACK_BASS));
  } else if (cmd == CMD_LEAD_VOL) {
    ApplyNudge(TRACK_LEAD, param);
  } else if (cmd == CMD_LEAD_MUTE_TOGGLE) {
    Track.Mute(TRACK_LEAD, !Track.IsMuted(TRACK_LEAD));
    Globals.Log("LEAD_MUTE_TOGGLE -> " + Track.IsMuted(TRACK_LEAD));
  } else if (cmd == CMD_DRUMS_VOL) {
    ApplyNudge(TRACK_DRUMS, param);
  } else if (cmd == CMD_DRUMS_MUTE_TOGGLE) {
    Track.Mute(TRACK_DRUMS, !Track.IsMuted(TRACK_DRUMS));
    Globals.Log("DRUMS_MUTE_TOGGLE -> " + Track.IsMuted(TRACK_DRUMS));
  } else if (cmd == CMD_FX_VOL) {
    ApplyNudge(TRACK_FX, param);
  } else if (cmd == CMD_FX_MUTE_TOGGLE) {
    Track.Mute(TRACK_FX, !Track.IsMuted(TRACK_FX));
    Globals.Log("FX_MUTE_TOGGLE -> " + Track.IsMuted(TRACK_FX));
  } else if (cmd == CMD_MASTER_VOL) {
    ApplyNudge(Track.MASTER_TRACK, param);

  } else if (cmd == CMD_SECTION_INTRO) {
    Perform.TriggerSet(COL_INTRO);
    Globals.Log("SECTION_INTRO -> TriggerSet(" + COL_INTRO + ")");
  } else if (cmd == CMD_SECTION_BUILD) {
    Perform.TriggerSet(COL_BUILD);
    Globals.Log("SECTION_BUILD -> TriggerSet(" + COL_BUILD + ")");
  } else if (cmd == CMD_SECTION_DROP) {
    Perform.TriggerSet(COL_DROP);
    Globals.Log("SECTION_DROP -> TriggerSet(" + COL_DROP + ")");
  } else if (cmd == CMD_SECTION_BREAK) {
    Perform.TriggerSet(COL_BREAK);
    Globals.Log("SECTION_BREAK -> TriggerSet(" + COL_BREAK + ")");
  } else if (cmd == CMD_SECTION_OUTRO) {
    Perform.TriggerSet(COL_OUTRO);
    Globals.Log("SECTION_OUTRO -> TriggerSet(" + COL_OUTRO + ")");
  } else if (cmd == CMD_EXTEND_SECTION) {
    // v1: re-trigger whatever column is currently playing in row 0 as a
    // simple "one more pass" gesture. bars param (0=8,1=16,2=32) is logged
    // but not yet used to pick a differently-sized clip -- that needs Iddo's
    // real Performance grid layout (which columns hold which bar-length
    // variants), unknown until the project exists. Documented as v1-partial
    // in the status report, not silently pretended to be complete.
    Globals.Log("EXTEND_SECTION bars_code=" + param + " (v1: logged only, see README 'what v1 does not do')");
  } else if (cmd == CMD_STOP_ALL_CLIPS) {
    Perform.StopAll();
    Globals.Log("STOP_ALL_CLIPS");

  } else {
    Globals.Log("UNKNOWN command id " + cmd + " param " + param + " -- ignored, not guessed");
  }
}

function OnSysEx(sysExData) {
  Globals.Log("OnSysEx received, length=" + sysExData.length + " (unused in v1)");
}

function OnTimer(timerID) {
  // no timers used in v1
}
