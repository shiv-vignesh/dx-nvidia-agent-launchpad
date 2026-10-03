#!/usr/bin/env bash
# App venv setup — runway's [venv].setup_script. runway creates /home/shiv/.venvs/shiftguard,
# activates it, then runs this from the project root. Installs ShiftGuard + dev deps (editable),
# so `import app...` and pytest work on the GB10 (the package lives in engine/). Pure-Python deps; no stack needed.
set -euo pipefail

echo "python: $(python --version)   pip: $(pip --version | awk '{print $2}')"
pip install --upgrade pip >/dev/null
pip install -e "./engine[dev]"
python -c "import pydantic, pytest, app.domain.engine as e; print('deps ok — pydantic', pydantic.VERSION)"
echo "== app venv ready =="
