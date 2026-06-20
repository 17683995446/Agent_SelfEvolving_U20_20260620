#!/bin/bash
# 启动脚本 - 使用统一CLI入口

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"

export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH}"

cd "${PROJECT_ROOT}"

python3 -m agent_core start "$@"
