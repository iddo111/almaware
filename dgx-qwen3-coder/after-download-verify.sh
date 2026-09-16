#!/usr/bin/env bash
set -euo pipefail

download_unit="qwen3-coder-download-lowmem.service"
model_dir="/home/eran1/models/Qwen3-Coder-480B-A35B-Instruct-GGUF/Q4_K_M"
runtime_dir="/home/eran1/qwen3-coder-runtime"
result_file="$runtime_dir/verification-result.json"
state_file="$runtime_dir/after-download-state.txt"
switched=0

rollback() {
  local rc=$?
  printf '%s FAIL rc=%s\n' "$(date --iso-8601=seconds)" "$rc" >"$state_file"
  if ((switched)); then
    "$runtime_dir/switch-model.sh" grok || true
  fi
  exit "$rc"
}
trap rollback ERR

while systemctl --user is-active --quiet "$download_unit"; do
  sleep 60
done

download_rc="$(systemctl --user show "$download_unit" -p ExecMainStatus --value)"
test "$download_rc" = "0"

declare -A expected=(
  [Qwen3-Coder-480B-A35B-Instruct-Q4_K_M-00001-of-00006.gguf]=49973553312
  [Qwen3-Coder-480B-A35B-Instruct-Q4_K_M-00002-of-00006.gguf]=49768927168
  [Qwen3-Coder-480B-A35B-Instruct-Q4_K_M-00003-of-00006.gguf]=48862488352
  [Qwen3-Coder-480B-A35B-Instruct-Q4_K_M-00004-of-00006.gguf]=48952192064
  [Qwen3-Coder-480B-A35B-Instruct-Q4_K_M-00005-of-00006.gguf]=49721298176
  [Qwen3-Coder-480B-A35B-Instruct-Q4_K_M-00006-of-00006.gguf]=42780367136
)

for name in "${!expected[@]}"; do
  path="$model_dir/$name"
  test -f "$path"
  actual="$(stat -c %s "$path")"
  test "$actual" = "${expected[$name]}"
done

printf '%s shards verified; switching to Qwen\n' "$(date --iso-8601=seconds)" >"$state_file"
switched=1
"$runtime_dir/switch-model.sh" qwen
/usr/bin/python3 "$runtime_dir/verify_qwen_code.py" >"$result_file"

if sudo -n tailscale serve --bg --yes --https=8448 8081 >/dev/null 2>&1; then
  serve_status="PASS"
else
  serve_status="FAIL"
fi

printf '%s PASS model=PASS code=PASS tailscale=%s\n' \
  "$(date --iso-8601=seconds)" "$serve_status" >"$state_file"
trap - ERR
