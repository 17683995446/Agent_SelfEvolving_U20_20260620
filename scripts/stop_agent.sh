#!/bin/bash
# 停止脚本

set -e

echo "[stop_agent] Stopping agent processes..."

pkill -f "agent_main" || true

echo "[stop_agent] Agent stopped."
