#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${project_dir}/.venv/bin/python"
config_path="${FOXALIEN_CONFIG:-${project_dir}/config/machine.json}"
console_url="http://127.0.0.1:8765"
log_dir="${project_dir}/logs"

if [[ ! -x "${python_bin}" ]]; then
  printf 'FoxAlien console is not installed.\nRun: %s/scripts/install_jetson.sh\n' "${project_dir}" >&2
  exit 1
fi

health_ok() {
  "${python_bin}" - "${console_url}/health" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

with urllib.request.urlopen(sys.argv[1], timeout=0.5) as response:
    if response.status != 200:
        raise SystemExit(1)
PY
}

if ! health_ok; then
  mkdir -p "${log_dir}"
  nohup "${python_bin}" -m foxalien_control.server \
    --config "${config_path}" \
    >"${log_dir}/console.log" 2>&1 &

  for _ in $(seq 1 40); do
    if health_ok; then
      break
    fi
    sleep 0.1
  done
fi

if ! health_ok; then
  printf 'Console did not start. Read %s/console.log\n' "${log_dir}" >&2
  exit 2
fi

if command -v chromium-browser >/dev/null 2>&1; then
  exec chromium-browser --app="${console_url}"
elif command -v chromium >/dev/null 2>&1; then
  exec chromium --app="${console_url}"
else
  exec xdg-open "${console_url}"
fi
