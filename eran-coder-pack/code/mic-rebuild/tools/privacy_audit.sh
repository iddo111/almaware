#!/usr/bin/env bash
# KESHEV gate-19 privacy audit — PC-side driver (PHASE2-DESIGN.md section 9,
# criterion 19; K11). Re-runnable at K17 (mid-soak: it detects a running
# server, uses it, and leaves it running).
#
#   bash tools/privacy_audit.sh
#
# Phases: Qwen pre-check -> deploy fresh server files -> unit verify +
# delegation -> start server if needed (start, NEVER enable) -> begin marker
# -> canary session (5 phrases, real DgxEngine path) -> eran1-side check
# (fs-diff, journal whitelist + canary grep, fd audit, coredumps, bind) ->
# auth probes from eran2 -> loopback/alt-interface bind probes -> stop server
# iff we started it -> Qwen post-check -> gate19-<date>.json.
#
# HARD GATE: no real speech leaves the PC before this prints verdict PASS.
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${KESHEV_HOST:-eran1}"
PROBE_HOST="${KESHEV_PROBE_HOST:-eran2}"
LAN_IP="<lan-ip>"
URL="http://$LAN_IP:8737/"
TOKEN_FILE="$REPO/state/stt-token"
WAV_DIR="$REPO/tools/replay/wavs/canary"
REPORT_DIR="$REPO/state/reports"
DATE="$(date +%Y%m%d)"
PY="${PYTHON:-python}"
STEPS=()          # NAME PASS|FAIL DETAIL triplets
FAILED=0

say()  { echo "[gate19] $*"; }
add_step() {  # name verdict detail
    STEPS+=("$1" "$2" "$3")
    [ "$2" = "PASS" ] || FAILED=1
    say "STEP $1 $2 - $3"
}

mkdir -p "$REPORT_DIR"

# ---------------------------------------------------------------- 0: qwen pre
q_pre=$(ssh "$HOST" 'curl -s -m 8 http://127.0.0.1:8080/health' 2>/dev/null || true)
if echo "$q_pre" | grep -q '"ok"'; then
    add_step qwen_before PASS "eran1:8080 answers: $q_pre"
else
    add_step qwen_before FAIL "Qwen head not healthy: '$q_pre' - refusing to continue"
    "$PY" -m tools.privacy_canaries report --out "$REPORT_DIR/gate19-$DATE.json" \
        --step qwen_before FAIL "unhealthy"; exit 1
fi

# ---------------------------------------------------------------- 1: deploy
say "deploying current server files to $HOST:~/keshev (repo is the truth)"
scp -q "$REPO/server/stt_server.py" "$REPO/server/sdnotify.py" \
       "$REPO/server/run_server.sh" "$REPO/server/server.json" \
       "$REPO/server/audit_privacy.sh" "$HOST:~/keshev/" || { say "scp failed"; exit 1; }
scp -q "$REPO"/common/*.py "$HOST:~/keshev/common/" || { say "scp common failed"; exit 1; }
scp -q "$REPO/server/keshev-stt.service" "$HOST:~/.config/systemd/user/keshev-stt.service"
ssh "$HOST" 'chmod +x ~/keshev/run_server.sh ~/keshev/audit_privacy.sh; rm -f ~/keshev/server.log ~/keshev/nohup.out; find ~/keshev -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; true'

# ---------------------------------------------------------------- 2: unit verify
verify=$(ssh "$HOST" 'systemctl --user daemon-reload && systemd-analyze --user verify ~/.config/systemd/user/keshev-stt.service 2>&1; echo RC=$?')
if echo "$verify" | grep -q 'RC=0'; then
    add_step unit_verify PASS "systemd-analyze verify clean; unit NOT enabled (enable is a cutover step)"
else
    add_step unit_verify FAIL "$verify"
fi

# ---------------------------------------------------------------- 3: token
if [ ! -s "$TOKEN_FILE" ]; then
    mkdir -p "$(dirname "$TOKEN_FILE")"
    ssh "$HOST" 'cat ~/.config/keshev-stt/token' > "$TOKEN_FILE"
fi
[ -s "$TOKEN_FILE" ] || { say "no token"; exit 1; }

# ---------------------------------------------------------------- 4: server up
was_active=$(ssh "$HOST" 'systemctl --user is-active keshev-stt' 2>/dev/null || true)
STARTED_BY_US=0
if [ "$was_active" != "active" ]; then
    say "starting keshev-stt (systemctl --user start - NOT enable)"
    ssh "$HOST" 'systemctl --user start keshev-stt' || {
        add_step unit_start FAIL "$(ssh "$HOST" 'systemctl --user status keshev-stt --no-pager -l | tail -20')"
        "$PY" -m tools.privacy_canaries report --out "$REPORT_DIR/gate19-$DATE.json" \
            --step unit_start FAIL "start failed"; exit 1; }
    STARTED_BY_US=1
else
    say "server already active (K17 mid-soak mode) - will leave it running"
fi

TOKEN="$(cat "$TOKEN_FILE")"
say "waiting for READY (models load ~10s)"
ready=""
for _ in $(seq 1 60); do
    h=$(curl -s -m 5 -H "Authorization: Bearer $TOKEN" "${URL}health" 2>/dev/null || true)
    if echo "$h" | grep -q '"state": *"READY"'; then ready="$h"; break; fi
    sleep 2
done
if [ -n "$ready" ]; then
    add_step server_ready PASS "$(echo "$ready" | head -c 200)"
else
    add_step server_ready FAIL "server never reached READY"
    ssh "$HOST" 'journalctl --user -u keshev-stt --since -5min -o cat | tail -30'
    [ "$STARTED_BY_US" = 1 ] && ssh "$HOST" 'systemctl --user stop keshev-stt'
    "$PY" -m tools.privacy_canaries report --out "$REPORT_DIR/gate19-$DATE.json" \
        --step server_ready FAIL "never READY"; exit 1
fi

# ---------------------------------------------------------------- 5: delegation
# Design section 6: verify the caps TOOK EFFECT, never assume. systemd 255
# has no EffectiveMemoryMax property (v256+), so read the unit's actual
# cgroup files — the ground truth the kernel enforces.
deleg=$(ssh "$HOST" '
    pid=$(systemctl --user show -p MainPID --value keshev-stt)
    cg=$(cut -d: -f3 /proc/$pid/cgroup | head -1)
    echo "memory.max=$(cat /sys/fs/cgroup$cg/memory.max 2>/dev/null)"
    echo "memory.high=$(cat /sys/fs/cgroup$cg/memory.high 2>/dev/null)"
    echo "memory.swap.max=$(cat /sys/fs/cgroup$cg/memory.swap.max 2>/dev/null)"
    echo "cpu.max=$(cat /sys/fs/cgroup$cg/cpu.max 2>/dev/null)"' 2>/dev/null)
if echo "$deleg" | grep -q '^memory.max=10737418240$' \
   && echo "$deleg" | grep -q '^memory.high=8589934592$' \
   && echo "$deleg" | grep -q '^memory.swap.max=0$' \
   && echo "$deleg" | grep -q '^cpu.max=400000 100000$'; then
    add_step delegation PASS "kernel-enforced cgroup caps: $(echo "$deleg" | tr '\n' ' ')"
else
    add_step delegation FAIL "caps did not take effect: $(echo "$deleg" | tr '\n' ' ')"
fi

# ---------------------------------------------------------------- 6: marker
begin_out=$(ssh "$HOST" 'bash ~/keshev/audit_privacy.sh begin')
say "$begin_out"

# settle so late startup writes (pycache etc.) would land BEFORE the marker
sleep 2

# ---------------------------------------------------------------- 7: canaries
say "sending 5 canary utterances through the real DgxEngine path"
if "$PY" -m tools.privacy_canaries send --url "$URL" --token-file "$TOKEN_FILE" \
        --wav-dir "$WAV_DIR" --out-json "$REPORT_DIR/canary-$DATE.json" \
        --out-intended "$REPORT_DIR/words-intended.txt" \
        --out-response "$REPORT_DIR/words-all.txt"; then
    add_step canary_decode PASS "5/5 phrases confirmed through the decoder"
else
    add_step canary_decode FAIL "not every canary phrase was confirmed decoded (grep would be vacuous)"
fi

# ---------------------------------------------------------------- 8: eran1 check
scp -q "$REPORT_DIR/words-intended.txt" "$REPORT_DIR/words-all.txt" "$HOST:~/keshev/audit/"
check_out=$(ssh "$HOST" 'bash ~/keshev/audit_privacy.sh check ~/keshev/audit/words-intended.txt ~/keshev/audit/words-all.txt'; echo "RC=$?")
echo "$check_out" | sed 's/^/[eran1] /'
while read -r _ name verdict detail; do
    add_step "$name" "$verdict" "$detail"
done < <(echo "$check_out" | grep '^STEP ')

# ---------------------------------------------------------------- 9: auth probes (from eran2)
say "auth probes from $PROBE_HOST (second LAN host)"
probes_ok=1; probe_detail=""
probe() {  # label curl-args... -> expects 401
    local label="$1"; shift
    local code
    code=$(ssh "$PROBE_HOST" "curl -s -o /dev/null -m 10 -w '%{http_code}' $*" 2>/dev/null || echo "ERR")
    probe_detail="$probe_detail $label=$code"
    [ "$code" = "401" ] || probes_ok=0
}
probe no_token_health         "http://$LAN_IP:8737/health"
probe wrong_token_health      "-H 'Authorization: Bearer $(printf '0%.0s' $(seq 64))' http://$LAN_IP:8737/health"
probe no_token_metrics        "http://$LAN_IP:8737/metrics"
probe no_token_drain          "-X POST http://$LAN_IP:8737/admin/drain"
probe no_token_body_post      "-X POST -H 'X-Request-Id: deadbeef-000001' --data-binary 'aabb' http://$LAN_IP:8737/v1/transcribe"
probe wrong_token_post        "-X POST -H 'Authorization: Bearer $(printf '1%.0s' $(seq 64))' -H 'X-Request-Id: deadbeef-000002' --data-binary 'aabb' http://$LAN_IP:8737/v1/transcribe"
if [ "$probes_ok" = 1 ]; then
    add_step auth_probes PASS "all unauth/wrong-token probes -> 401:$probe_detail"
else
    add_step auth_probes FAIL "expected 401 everywhere:$probe_detail"
fi

# ---------------------------------------------------------------- 10: non-configured interfaces refuse
say "bind probes: loopback + every non-LAN address on $HOST must refuse"
alt_out=$(ssh "$HOST" '
    fails=""; oks=""
    for ip in 127.0.0.1 $(ip -4 -o addr show scope global 2>/dev/null | awk "{print \$4}" | cut -d/ -f1); do
        [ "$ip" = "<lan-ip>" ] && continue
        if curl -s -o /dev/null -m 4 "http://$ip:8737/health" 2>/dev/null; then
            fails="$fails $ip"
        else
            oks="$oks $ip"
        fi
    done
    echo "REFUSED:$oks OPEN:$fails"')
if echo "$alt_out" | grep -q 'OPEN: *$'; then
    add_step iface_probes PASS "$alt_out"
else
    add_step iface_probes FAIL "$alt_out"
fi

# ---------------------------------------------------------------- 11: stop iff we started
if [ "$STARTED_BY_US" = 1 ]; then
    ssh "$HOST" 'systemctl --user stop keshev-stt'
    port_after=$(ssh "$HOST" 'ss -tln | grep ":8737 " || echo free')
    say "server stopped; port state: $port_after"
else
    say "leaving the already-running server up (mid-soak mode)"
fi

# ---------------------------------------------------------------- 12: qwen post
q_post=$(ssh "$HOST" 'curl -s -m 8 http://127.0.0.1:8080/health' 2>/dev/null || true)
if echo "$q_post" | grep -q '"ok"'; then
    add_step qwen_after PASS "eran1:8080 still healthy: $q_post"
else
    add_step qwen_after FAIL "Qwen head unhealthy after audit: '$q_post'"
fi

# ---------------------------------------------------------------- 13: report
args=()
i=0
while [ $i -lt ${#STEPS[@]} ]; do
    args+=(--step "${STEPS[$i]}" "${STEPS[$((i+1))]}" "${STEPS[$((i+2))]}")
    i=$((i+3))
done
"$PY" -m tools.privacy_canaries report --out "$REPORT_DIR/gate19-$DATE.json" "${args[@]}"
rc=$?
say "report: $REPORT_DIR/gate19-$DATE.json"
exit $rc
