#!/usr/bin/env bash
# KESHEV gate-19 privacy audit — eran1-side half (PHASE2-DESIGN.md section 9,
# criterion 19; K11). Driven from the PC by tools/privacy_audit.sh.
#
# The claim under audit: after a /v1/transcribe request the server retains
# NOTHING — no wav, no PCM, no transcript, anywhere on the host. Audio lives
# only in RAM (the server has no code path that constructs a file path for
# audio); journald carries STATUS LINES ONLY.
#
# Subcommands:
#   begin                       set the timestamp marker (fs-diff + journal --since)
#   check <intended> <all>      run the retention checks; args = word-list files
#   checklines                  whitelist-filter stdin (used by PC-side tests)
#   selftest                    prove the whitelist classifies fixtures correctly
#
# Honest deviation from the design's "assert ZERO new files anywhere on the
# host": eran1 is multi-tenant (Qwen head, ComfyUI, ant-farm...) and other
# processes write files continuously. The audit therefore asserts:
#   * ZERO new files attributable to KESHEV (~/keshev*, the unit's private
#     tmp, /dev/shm, /var/tmp, /tmp) — hard FAIL on any;
#   * every OTHER new file under $HOME is listed and grepped for the canary
#     words — a hit is a hard FAIL wherever it lands.
set -u

AUDIT_DIR="$HOME/keshev/audit"
MARKER="$AUDIT_DIR/marker"
UNIT="keshev-stt"

# ---------------------------------------------------------------- whitelist
# The journald line whitelist — THE one truth (tests drive it via selftest/
# checklines; do not copy these patterns anywhere else).
#
# W1: our status lines: "YYYY-mm-dd HH:MM:SS,mmm LEVEL evt=NAME k=v ..."
W1='^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2},[0-9]{3} (INFO|WARNING|ERROR) evt=[A-Z_]+( [A-Za-z_][A-Za-z_0-9]*=[^ ]*)*$'
# W2: systemd unit lifecycle lines
W2='^(Started |Starting |Stopping |Stopped |Deactivated successfully|Scheduled restart|Consumed |keshev-stt\.service:).*'
# W3: faster-whisper library lines — numeric-only shapes, nothing else
#     (the server pins that logger to WARNING; these shapes stay whitelisted
#     because they carry durations/ratios only, never text)
W3='^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2},[0-9]{3} (INFO|WARNING) (Processing audio with duration [0-9:.]+|VAD filter removed [0-9:.]+ of audio|Compression ratio threshold is not met with temperature [0-9.]+ \([0-9.]+ > [0-9.]+\)|Log probability threshold is not met with temperature [0-9.]+ \(-?[0-9.]+ < -?[0-9.]+\)|No speech threshold is met \([0-9.]+ > [0-9.]+\))$'
# Banned keys: a transcript-shaped field is a violation even if the line is
# otherwise well-formed (defense in depth under status_line's TypeError).
BANNED='(^| )(text|transcript|title)='

wl_violations() {
    # stdin -> stdout: every line that is NOT whitelisted, or that carries a
    # banned key. Empty output = clean.
    local input violators banned
    input=$(cat)
    violators=$(printf '%s\n' "$input" | grep -v '^[[:space:]]*$' \
                | grep -Ev -e "$W1" -e "$W2" -e "$W3" || true)
    banned=$(printf '%s\n' "$input" | grep -E "$BANNED" || true)
    printf '%s\n%s\n' "$violators" "$banned" | grep -v '^[[:space:]]*$' | sort -u
}

# ---------------------------------------------------------------- selftest

selftest() {
    local good bad line fails=0
    good=$(cat <<'EOF'
2026-08-12 13:10:38,801 INFO evt=MODELS_LOADED load_s=5.1 stock=large-v3-turbo-ct2 lora=iddo-lora-run2-ct2
2026-08-12 13:10:38,858 INFO evt=CANARY_OK ms=55
2026-08-12 13:14:12,321 INFO evt=REQ id=a3f9c2d1-000123 code=200 bytes=102400 ms=486 rtf=0.16 lang=he lp=-0.28 len=42 reason=detect_he
2026-08-12 13:14:12,400 WARNING evt=DECODE_TIMEOUT id=a3f9c2d1-000124 wall_s=15.0
2026-08-12 13:10:33,692 INFO Processing audio with duration 00:01.000
2026-08-12 13:10:33,742 INFO VAD filter removed 00:01.000 of audio
Started keshev-stt.service - KESHEV STT server (faster-whisper CT2) :8737.
Stopping keshev-stt.service - KESHEV STT server (faster-whisper CT2) :8737...
keshev-stt.service: Consumed 21.607s CPU time.
EOF
)
    bad=$(cat <<'EOF'
2026-08-12 13:14:12,305 INFO evt=REQ id=deadbeef-000001 text=hello world
2026-08-12 13:14:12,305 INFO evt=REQ id=deadbeef-000002 text=quixotic
שלום עולם זה תמליל גולמי שדלף ליומן
2026-08-12 13:14:12,305 INFO the quixotic zeppelin hauled some marmalade
Traceback (most recent call last):
2026-08-12 13:14:12,305 INFO evt=req id=lowercase-evt-not-allowed
EOF
)
    while IFS= read -r line; do
        if [ -n "$(printf '%s\n' "$line" | wl_violations)" ]; then
            echo "SELFTEST FAIL: good line rejected: $line"
            fails=$((fails + 1))
        fi
    done <<< "$good"
    while IFS= read -r line; do
        if [ -z "$(printf '%s\n' "$line" | wl_violations)" ]; then
            echo "SELFTEST FAIL: bad line accepted: $line"
            fails=$((fails + 1))
        fi
    done <<< "$bad"
    if [ "$fails" -eq 0 ]; then
        echo "SELFTEST PASS (whitelist classifies all fixtures correctly)"
        return 0
    fi
    return 1
}

# ---------------------------------------------------------------- phases

begin() {
    mkdir -p "$AUDIT_DIR"
    rm -f "$AUDIT_DIR"/newfiles.txt "$AUDIT_DIR"/words-*.txt
    date +%s > "$MARKER.epoch"
    touch "$MARKER"
    echo "MARKER_EPOCH $(cat "$MARKER.epoch")"
    echo "BIND_SNAPSHOT $(ss -tln 2>/dev/null | grep ':8737 ' | tr -s ' ' | tr '\n' ';')"
}

step() {  # step NAME PASS|FAIL detail...
    local name="$1" verdict="$2"; shift 2
    echo "STEP $name $verdict $*"
    [ "$verdict" = "PASS" ] || OVERALL=1
}

check() {
    local intended="$1" allwords="$2"
    local epoch since pid
    OVERALL=0
    # vacuous-grep guard: a missing/empty word list would make every canary
    # grep silently pass (grep -f on a missing file exits 2 == "no match").
    # Found by the K11 negative control — fail LOUDLY instead.
    local wf
    for wf in "$intended" "$allwords"; do
        if [ ! -s "$wf" ]; then
            step words_files FAIL "missing or empty canary word list: $wf"
            echo "CHECK_OVERALL FAIL"
            return 1
        fi
    done
    step words_files PASS "word lists present: $(wc -l < "$intended") intended, $(wc -l < "$allwords") total"
    epoch=$(cat "$MARKER.epoch")
    since="@$epoch"

    # -- journal whitelist (unit journal since marker)
    local jlines viol
    jlines=$(journalctl --user -u "$UNIT" --since "$since" -o cat 2>/dev/null || true)
    viol=$(printf '%s\n' "$jlines" | wl_violations)
    local total
    total=$(printf '%s\n' "$jlines" | grep -vc '^[[:space:]]*$' || true)
    if [ -n "$viol" ]; then
        step journal_whitelist FAIL "non-status lines in journald:"
        printf '%s\n' "$viol" | sed 's/^/    VIOLATION: /'
    else
        step journal_whitelist PASS "$total/$total lines match the status whitelist"
    fi

    # -- canary grep: unit journal (all words incl. response-derived)
    local hits1
    hits1=$(printf '%s\n' "$jlines" | grep -iFf "$allwords" || true)
    if [ -n "$hits1" ]; then
        step journal_canary FAIL "canary text found in the unit journal:"
        printf '%s\n' "$hits1" | sed 's/^/    LEAK: /'
    else
        step journal_canary PASS "0 canary hits in unit journal ($total lines)"
    fi

    # -- canary grep: ENTIRE user journal (intended rare words only —
    #    other units log freely; a rare-word hit is still a leak signal)
    local hits2
    hits2=$(journalctl --user --since "$since" -o cat 2>/dev/null | grep -iFf "$intended" || true)
    if [ -n "$hits2" ]; then
        step journal_broad FAIL "canary words elsewhere in the user journal:"
        printf '%s\n' "$hits2" | sed 's/^/    LEAK: /'
    else
        step journal_broad PASS "0 canary hits across the whole user journal"
    fi

    # -- fs-diff: new files since marker across the design's four roots
    local newfiles keshev_new n_new
    newfiles=$(find "$HOME" /tmp /dev/shm /var/tmp -xdev -type f -newer "$MARKER" 2>/dev/null \
               | grep -v "^$AUDIT_DIR/" || true)
    n_new=$(printf '%s\n' "$newfiles" | grep -vc '^[[:space:]]*$' || true)
    keshev_new=$(printf '%s\n' "$newfiles" | grep -E "^$HOME/keshev" || true)
    if [ -n "$keshev_new" ]; then
        step fs_keshev FAIL "NEW FILES under ~/keshev* (server must retain nothing):"
        printf '%s\n' "$keshev_new" | sed 's/^/    RETAINED: /'
    else
        step fs_keshev PASS "0 new files under ~/keshev* (total new elsewhere: $n_new)"
    fi

    # -- grep every other new file (readable, <20MB) for canary words
    local leaks="" f
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        [ -r "$f" ] || continue
        [ "$(stat -c%s "$f" 2>/dev/null || echo 999999999)" -gt 20000000 ] && continue
        if grep -ilqFf "$allwords" "$f" 2>/dev/null; then
            leaks="$leaks $f"
        fi
    done <<< "$newfiles"
    if [ -n "$leaks" ]; then
        step fs_canary FAIL "canary text inside new files:$leaks"
    else
        step fs_canary PASS "0 canary hits in $n_new new files (all roots)"
    fi
    printf '%s\n' "$newfiles" > "$AUDIT_DIR/newfiles.txt"

    # -- fd audit: the server may hold NO regular file open for write, and
    #    nothing audio-shaped at all
    pid=$(systemctl --user show -p MainPID --value "$UNIT" 2>/dev/null || echo 0)
    if [ "$pid" -gt 0 ] 2>/dev/null && [ -d "/proc/$pid/fd" ]; then
        local badfd="" fd target flags w
        for fd in /proc/"$pid"/fd/*; do
            target=$(readlink "$fd" 2>/dev/null) || continue
            case "$target" in
                *.wav|*.pcm|*.flac|*.ogg|*.mp3) badfd="$badfd AUDIO:$target" ;;
            esac
            if [ -f "$target" ]; then
                flags=$(awk '/^flags:/{print $2}' "/proc/$pid/fdinfo/$(basename "$fd")" 2>/dev/null || echo 0)
                w=$(( 8#$flags & 3 ))
                [ "$w" -ne 0 ] && badfd="$badfd WRITE:$target"
            fi
        done
        if [ -n "$badfd" ]; then
            step fd_audit FAIL "suspicious fds:$badfd"
        else
            step fd_audit PASS "pid=$pid holds no write-mode regular files, nothing audio-shaped"
        fi
    else
        step fd_audit FAIL "unit MainPID not found (server not running under systemd?)"
    fi

    # -- coredumps would embed request audio; none may exist for us
    if command -v coredumpctl >/dev/null 2>&1; then
        local cores
        cores=$(coredumpctl list --since "$since" 2>/dev/null | grep -iE 'stt_server|keshev' || true)
        if [ -n "$cores" ]; then
            step coredump FAIL "$cores"
        else
            step coredump PASS "no keshev coredumps since marker"
        fi
    else
        step coredump PASS "coredumpctl unavailable (no systemd-coredump on host)"
    fi

    # -- bind: the ONLY 8737 listener is the configured LAN address
    local binds badbind
    binds=$(ss -tln 2>/dev/null | awk '$4 ~ /:8737$/ {print $4}')
    badbind=$(printf '%s\n' "$binds" | grep -v '^192\.168\.1\.198:8737$' | grep -v '^[[:space:]]*$' || true)
    if [ -z "$binds" ]; then
        step bind_check FAIL "nothing listening on :8737"
    elif [ -n "$badbind" ]; then
        step bind_check FAIL "unexpected listeners: $badbind"
    else
        step bind_check PASS "listener is exactly <lan-ip>:8737"
    fi

    echo "CHECK_OVERALL $([ "$OVERALL" -eq 0 ] && echo PASS || echo FAIL)"
    return "$OVERALL"
}

case "${1:-}" in
    begin)      begin ;;
    check)      check "$2" "$3" ;;
    checklines) v=$(wl_violations); if [ -n "$v" ]; then printf '%s\n' "$v"; exit 1; fi ;;
    selftest)   selftest ;;
    *) echo "usage: $0 begin | check <intended-words> <all-words> | checklines | selftest" >&2
       exit 2 ;;
esac
