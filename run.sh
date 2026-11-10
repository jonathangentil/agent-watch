#!/usr/bin/env sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/alethe-tui ]; then
    echo 'Instale o projeto com: uv sync --extra dev' >&2
    exit 1
fi
exec .venv/bin/alethe-tui "$@"
