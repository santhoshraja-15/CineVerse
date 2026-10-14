#!/usr/bin/env sh
# Lint and fast test suite (Repository Standards §9).
set -e
ruff check .
python -m pytest -q -m "not full"
