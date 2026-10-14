# Lint and fast test suite (Repository Standards §9).
$ErrorActionPreference = "Stop"
ruff check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m pytest -q -m "not full"
exit $LASTEXITCODE
