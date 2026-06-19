#!/bin/bash
# 测试执行脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"

export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH}"

cd "${PROJECT_ROOT}"

echo "[run_tests] Running unit tests..."

python3 -m unittest discover -s tests -v

echo "[run_tests] Tests completed."
