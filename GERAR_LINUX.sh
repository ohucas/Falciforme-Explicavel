#!/usr/bin/env bash
set -euo pipefail
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python -m PyInstaller --noconfirm --clean --windowed --onedir --name FalciformeExplicavel --add-data 'assets:assets' desktop.py
printf '%s\n' 'Saída: dist/FalciformeExplicavel/FalciformeExplicavel. Mantenha a pasta inteira.'
