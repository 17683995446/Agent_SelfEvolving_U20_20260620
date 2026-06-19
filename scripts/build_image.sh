#!/bin/bash
# Docker镜像构建脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"

cd "${PROJECT_ROOT}"

echo "[build_image] Building Docker image..."

docker build -t self_evolving_agent:1.0.0 -f Dockerfile .

echo "[build_image] Image built successfully."
