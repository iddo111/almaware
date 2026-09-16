#!/usr/bin/env bash
set -euo pipefail

lab_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv_dir="$lab_dir/.venv"

if [[ ! -x "$venv_dir/bin/python" ]]; then
  python3 -m venv "$venv_dir"
fi

"$venv_dir/bin/python" -m pip install --disable-pip-version-check -r "$lab_dir/requirements-local.txt"
"$venv_dir/bin/python" "$lab_dir/memristor_crossbar_demo.py"
"$venv_dir/bin/python" "$lab_dir/spiking_lif_demo.py"
"$venv_dir/bin/python" "$lab_dir/reservoir_demo.py"

