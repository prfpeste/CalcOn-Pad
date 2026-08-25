#!/usr/bin/env bash
set -euo pipefail

# Change to this script's directory
cd "$(dirname "$0")"

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

pip install pyinstaller
pip install -r requirements.txt

python -m PyInstaller \
  --clean \
  --onefile \
  --name EngiPad \
  --add-data "templates:templates" \
  --add-data "static:static" \
  run.py

mv dist/EngiPad EngiPad
rm -rf build dist EngiPad.spec .venv
