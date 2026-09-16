#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_dir="${project_dir}/.venv"
desktop_dir="${HOME}/.local/share/applications"
desktop_file="${desktop_dir}/foxalien-xe-pro-console.desktop"

python3 -m venv "${venv_dir}"
"${venv_dir}/bin/python" -m pip install --upgrade pip
"${venv_dir}/bin/python" -m pip install -r "${project_dir}/requirements.txt"
chmod +x "${project_dir}/scripts/launch_gui.sh"

"${venv_dir}/bin/python" -m unittest discover -s "${project_dir}/tests" -v

mkdir -p "${desktop_dir}"
sed "s|@PROJECT_DIR@|${project_dir}|g" \
  "${project_dir}/scripts/foxalien-console.desktop.in" >"${desktop_file}"
chmod +x "${desktop_file}"

echo "Installed and tested."
echo "Open 'FoxAlien XE-PRO Console' from the Ubuntu application menu,"
echo "or run: ${project_dir}/scripts/launch_gui.sh"
