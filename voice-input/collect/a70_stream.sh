#!/data/data/com.termux/files/usr/bin/bash
# ============================================================================
#  a70_stream.sh — A70 phone 24/7 audio COLLECTION streamer (Termux)
#
#  Records short audio chunks continuously and POSTs each one to the PC's
#  canonical collection endpoint  (POST /sample)  over Tailscale. If the PC is
#  unreachable, the chunk is parked in a local OFFLINE QUEUE on the phone and
#  re-sent automatically once the link is back — so nothing is lost on walks,
#  in the elevator, on the subway, etc.
#
#  >>> The PC endpoint is  D:\CLAUDE\hebrew-voice\collect_server.py  (port 8732).
#      That server runs the SAME owner+quality gate as the locked mic: it
#      transcribes on CPU, verifies the speaker is Iddo (voiceprint), and only
#      then appends owner-verified clips to the clean training corpus. So this
#      phone can stream ALL day — TV, other people, silence get dropped on the
#      PC; only Iddo's real speech is kept. This script just feeds it audio.
#
#  This phone-side streamer NEVER touches the locked PC mic. It only uploads.
#
#  ---------------------------------------------------------------------------
#  CONTRACT (matches hebrew-voice/collect_server.py):
#     POST http://<PC>:8732/sample?token=<TOKEN>
#          multipart audio=@chunk.m4a  +  device_id=a70
#     ->  {"ok":true,"accepted":true|false,"reason":"...", ...}
#     (accepted:false just means the PC gate dropped it — silence/TV/not-owner.
#      That is NORMAL and still counts as a successful upload: we delete the
#      local chunk either way, because the PC has made its decision on it.)
#  ---------------------------------------------------------------------------
#
#  >>> STAGED ON PC — NOT auto-deployed. Needs the phone in-hand once to:
#       Termux + Termux:API + Termux:Boot install, mic permission, tailscale up,
#       and the shared TOKEN. See the DEPLOY block at the bottom of this file.
#
#  Stop:   touch ~/.a70-collect/STOP        (loop exits at next cycle)
#  Tune:   env vars below, or a ~/.a70-collect/env file (PC=..., TOKEN=...).
#
#  לזכרה של עלמה ז"ל — iddoperez.ai
# ============================================================================
set -u

# ── config (override via env or ~/.a70-collect/env) ─────────────────────────
WORK="${WORK:-$HOME/.a70-collect}"
mkdir -p "$WORK"
[ -f "$WORK/env" ] && . "$WORK/env"          # optional persisted overrides

PC="${PC:-<tailnet-ip>}"          # eran1 (PC) Tailscale IP — verified 2026-06-17
PORT="${PORT:-8732}"               # collect_server.py port (the corpus writer)
TOKEN="${TOKEN:-}"                 # REQUIRED — must match COLLECT_TOKEN on the PC
DEVICE_ID="${DEVICE_ID:-a70}"      # provenance label stored with each clip
ENDPOINT="${ENDPOINT:-http://$PC:$PORT/sample}"
HEALTH="${HEALTH:-http://$PC:$PORT/health}"
SEG="${SEG:-10}"                   # seconds of audio per chunk
SR="${SR:-16000}"                  # sample rate (16 kHz mono = corpus standard)
HTTP_TIMEOUT="${HTTP_TIMEOUT:-30}" # seconds per upload attempt (PC does STT, allow time)
GAP="${GAP:-0}"                    # extra seconds of silence between chunks (0 = back-to-back)
QUEUE_MAX_MB="${QUEUE_MAX_MB:-2048}"  # cap offline queue size (drops OLDEST when over)
MIN_BYTES="${MIN_BYTES:-4000}"     # skip near-empty recordings (mic glitch)

QUEUE="$WORK/queue"; mkdir -p "$QUEUE"
STOP="$WORK/STOP";  rm -f "$STOP"
LOG="$WORK/stream.log"
SEQ_FILE="$WORK/seq"; [ -f "$SEQ_FILE" ] || echo 0 > "$SEQ_FILE"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }

if [ -z "$TOKEN" ]; then
  termux-toast "חסר TOKEN — ערוך ~/.a70-collect/env" 2>/dev/null
  log "FATAL no TOKEN set (the PC corpus endpoint is token-gated)."
  echo "ERROR: set TOKEN (e.g. printf 'TOKEN=<secret>\n' >> ~/.a70-collect/env)" >&2
  exit 1
fi

# ── deps check (fail loud, once) ────────────────────────────────────────────
for bin in termux-microphone-record curl date stat; do
  command -v "$bin" >/dev/null 2>&1 || {
    termux-toast "חסר: $bin (pkg install termux-api curl coreutils)" 2>/dev/null
    log "FATAL missing dependency: $bin"; exit 1; }
done

# keep the CPU awake so Android doesn't freeze the loop in deep sleep
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock
termux-toast "A70 collect: מקליט 24/7" 2>/dev/null
log "START endpoint=$ENDPOINT seg=${SEG}s sr=$SR queue=$QUEUE"

cleanup() {
  command -v termux-wake-unlock >/dev/null 2>&1 && termux-wake-unlock
  log "STOP"
  exit 0
}
trap cleanup INT TERM

# ── helpers ─────────────────────────────────────────────────────────────────

next_seq() {
  local n; n=$(cat "$SEQ_FILE" 2>/dev/null || echo 0)
  n=$((n + 1)); echo "$n" > "$SEQ_FILE"; echo "$n"
}

# Upload one queued file to the PC /sample endpoint.
# Returns 0 if the PC RECEIVED + RULED on it (HTTP 200, whether accepted or
# gate-dropped) -> safe to delete locally. Returns 1 if it should be RETRIED
# later (offline / timeout / 5xx, AND a 401 bad-token, since that is almost
# always a misconfig the user will fix — we must NOT silently discard audio
# over a typo'd token).
send_file() {
  local f="$1" code
  code=$(curl -s -o /dev/null -w '%{http_code}' -m "$HTTP_TIMEOUT" \
            -F "audio=@$f" -F "device_id=$DEVICE_ID" \
            "$ENDPOINT?token=$TOKEN" 2>/dev/null)
  case "$code" in
    200|400|413) return 0 ;;   # PC answered & decided (200=gate ruled; 400/413=
                               # this clip is malformed/too big — never deletable
                               # by retry, so drop it and move on).
    401)
      log "AUTH 401 — TOKEN does not match the PC (fix ~/.a70-collect/env); keeping $(basename "$f") queued"
      return 1 ;;              # keep the audio; the user will fix the token.
    *) return 1 ;;            # 000/5xx/empty => link/server down => requeue.
  esac
}

# trim queue to QUEUE_MAX_MB by deleting the OLDEST chunks first
trim_queue() {
  local kb cap_kb f
  cap_kb=$(( QUEUE_MAX_MB * 1024 ))
  kb=$(du -sk "$QUEUE" 2>/dev/null | cut -f1)
  [ -z "$kb" ] && return 0
  while [ "$kb" -gt "$cap_kb" ]; do
    f=$(ls -1tr "$QUEUE" 2>/dev/null | head -n1)
    [ -z "$f" ] && break
    rm -f "$QUEUE/$f"
    log "queue over cap (${kb}KB > ${cap_kb}KB) -> dropped oldest $f"
    kb=$(du -sk "$QUEUE" 2>/dev/null | cut -f1)
  done
}

# drain the offline queue oldest-first; stop early if a send fails (still offline)
drain_queue() {
  local f
  for f in $(ls -1tr "$QUEUE" 2>/dev/null); do
    [ -f "$STOP" ] && return
    if send_file "$QUEUE/$f"; then
      rm -f "$QUEUE/$f"
      log "drained $f"
    else
      log "drain paused (still offline) at $f"
      return    # network down again — keep the rest queued
    fi
  done
}

# ── main loop ────────────────────────────────────────────────────────────────
RAW="$WORK/rec.m4a"
while [ ! -f "$STOP" ]; do
  rm -f "$RAW"
  # record one chunk (AAC in m4a; compact + good enough; PC re-encodes to 16k wav)
  termux-microphone-record -f "$RAW" -l "$SEG" -e aac -r "$SR" -c 1 >/dev/null 2>&1
  sleep $((SEG + 1))
  termux-microphone-record -q >/dev/null 2>&1

  if [ ! -s "$RAW" ]; then
    log "empty recording (mic busy/denied?) — retry in 2s"
    sleep 2; continue
  fi
  sz=$(stat -c%s "$RAW" 2>/dev/null || echo 0)
  if [ "$sz" -lt "$MIN_BYTES" ]; then
    log "chunk too small ($sz bytes) — skip"
    rm -f "$RAW"; [ "$GAP" -gt 0 ] && sleep "$GAP"; continue
  fi

  seq=$(next_seq)
  epoch=$(date +%s)
  qf="$QUEUE/${epoch}_${seq}_${SEG}.m4a"
  mv "$RAW" "$qf"

  # try to send immediately; on transport failure it stays in the queue
  if send_file "$qf"; then
    rm -f "$qf"
  else
    log "offline — queued $qf (drain when link returns)"
    trim_queue
  fi

  # opportunistically drain any backlog (cheap when queue is empty)
  drain_queue

  [ "$GAP" -gt 0 ] && sleep "$GAP"
done
cleanup

# ============================================================================
#  DEPLOY (run on the A70, phone in-hand the first time)
#  --------------------------------------------------------------------------
#  PREREQS THAT REQUIRE THE PHONE IN HAND (cannot be scripted from the PC):
#    * Install from F-Droid (NOT Play Store — Play builds are stale):
#        Termux, Termux:API, Termux:Boot
#    * Grant Termux the MICROPHONE permission (Android prompt, tap Allow).
#    * Tailscale Android app: sign in as iddo111@ and toggle the VPN ON.
#      (Interactive login — a human must tap through Google/SSO once.)
#    * The shared TOKEN must match the PC's COLLECT_TOKEN (typed once).
#
#  ONE-TIME SETUP (in Termux on the phone):
#    1) pkg update && pkg install -y termux-api curl coreutils
#    2) termux-microphone-record -d -l 1 -f /dev/null   # fires the mic perm prompt -> Allow
#    3) The A70 is already on the tailnet as `a70` (<tailnet-ip>); the PC is
#       eran1 (<tailnet-ip>). Verify reachability + that the endpoint is up:
#         curl "http://<tailnet-ip>:8732/health"        # expect {"ok":true,...}
#    4) Drop in config (PC IP + the shared token) so you never edit the script:
#         mkdir -p ~/.a70-collect
#         printf 'PC=<tailnet-ip>\nTOKEN=PUT_THE_SAME_SECRET_AS_THE_PC\n' > ~/.a70-collect/env
#    5) Put this script on the phone + make it executable:
#         #   scp D:\CLAUDE\voice-input\collect\a70_stream.sh a70:~/a70_stream.sh   (from the PC)
#         chmod +x ~/a70_stream.sh
#    6) Smoke-test for ~30s, then check the PC corpus grew:
#         bash ~/a70_stream.sh        # speak a Hebrew sentence; Ctrl-C to stop
#         tail -f ~/.a70-collect/stream.log
#
#  AUTOSTART AT BOOT (Termux:Boot):
#    7) mkdir -p ~/.termux/boot
#       cp ~/a70_stream.sh ~/.termux/boot/a70_stream.sh
#       chmod +x ~/.termux/boot/a70_stream.sh
#       # open the Termux:Boot app ONCE so Android arms the boot receiver, then reboot
#
#  CONTROL:
#    Stop the loop:   touch ~/.a70-collect/STOP
#    Restart:         bash ~/a70_stream.sh   (or reboot, with Termux:Boot armed)
#    Watch log:       tail -f ~/.a70-collect/stream.log
#    Queue depth:     ls ~/.a70-collect/queue | wc -l   (0 = all uploaded)
# ============================================================================
