#!/bin/bash
# Reference solution entrypoint. NOT copied into the agent's /app --
# exists purely so maintainers can prove the task is solvable end-to-end
# inside the real container (docker build + live mongod).
set -euo pipefail
cd "$(dirname "$0")"
python3 migrate.py
