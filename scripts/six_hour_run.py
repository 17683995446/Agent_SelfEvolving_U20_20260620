"""
六小时长时间运行验证脚本。

启动Agent，记录所有日志到文件，每10分钟采样一次状态，
运行结束后生成详细报告。
"""

import asyncio
import json
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List

from agent_core.common.di_container import reset_di_container
from agent_core.memory.agent_main import SelfEvolvingAgent

_LOG_FILE = Path("/workspace/logs/six_hour_run.log")
_REPORT_FILE = Path("/workspace/logs/six_hour_report.json")
_SNAPSHOT_FILE = Path("/workspace/logs/six_hour_snapshots.jsonl")

_DURATION_SECONDS = 6 * 3600.0
_SAMPLE_INTERVAL = 60.0


def _log(msg: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _save_snapshot(snapshot: Dict[str, Any]) -> None:
    _SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_SNAPSHOT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, default=str) + "\n")


async def run_agent(duration_seconds: float = _DURATION_SECONDS) -> dict:
    """运行Agent指定时长并收集指标。"""
    reset_di_container()
    agent = SelfEvolvingAgent()

    config = {
        "perception": {},
        "drive_engine": {},
        "predictor": {"feature_dimensions": 10},
        "task_generator": {"exploration_rate": 0.3},
        "decision_engine": {"epsilon": 0.2},
        "memory": {
            "memory_capacity": 10000,
            "db_path": "six_hour_memory.db",
        },
        "dashboard_port": 0,
    }

    _log("=" * 60)
    _log("开始六小时长时间运行验证")
    _log("=" * 60)

    await agent.initialize(config)
    _log("Agent初始化完成")

    health = await agent.health_check()
    _log(f"初始健康状态: {health['status']}")

    await agent.start(
        online_interval_seconds=1.0,
        offline_interval_seconds=30.0,
    )
    _log("Agent双循环已启动 (在线1秒/周期, 离线30秒/周期)")

    start_time = time.time()
    cycle_count_start = agent._cycle_count
    errors_collected: List[float] = []
    rewards_collected: List[float] = []
    tasks_executed = 0
    crash_count = 0
    sample_count = 0

    while time.time() - start_time < duration_seconds:
        try:
            await asyncio.sleep(_SAMPLE_INTERVAL)
            elapsed = time.time() - start_time
            cycles = agent._cycle_count - cycle_count_start
            errors_collected.extend(agent._recent_errors[-10:])
            rewards_collected.extend(agent._recent_rewards[-10:])

            if agent._current_task is not None:
                tasks_executed += 1

            sample_count += 1
            snapshot = {
                "sample_index": sample_count,
                "elapsed_seconds": round(elapsed, 1),
                "elapsed_hours": round(elapsed / 3600, 2),
                "total_cycles": cycles,
                "cycles_per_minute": round(cycles / (elapsed / 60), 2),
                "recent_errors": list(agent._recent_errors[-5:]),
                "recent_rewards": list(agent._recent_rewards[-5:]),
                "current_task_type": (
                    agent._current_task.task_type
                    if agent._current_task else None
                ),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            _save_snapshot(snapshot)

            _log(
                f"[{sample_count}] 已运行 {elapsed/3600:.2f}小时, "
                f"周期数 {cycles}, 任务 {agent._current_task}"
            )
        except Exception as exc:
            crash_count += 1
            _log(f"!!! 采样异常 (第{crash_count}次): {exc}")
            _log(traceback.format_exc())

    _log("运行时间到达，准备停止...")
    try:
        await agent.stop()
    except Exception as exc:
        _log(f"停止时异常: {exc}")
        crash_count += 1

    total_cycles = agent._cycle_count - cycle_count_start
    elapsed_total = time.time() - start_time

    report: Dict[str, Any] = {
        "duration_seconds": round(elapsed_total, 1),
        "duration_hours": round(elapsed_total / 3600, 2),
        "total_cycles": total_cycles,
        "cycles_per_hour": round(total_cycles / (elapsed_total / 3600), 2),
        "tasks_executed": tasks_executed,
        "crash_count": crash_count,
        "sample_count": sample_count,
        "final_health": health,
        "avg_error": (
            sum(errors_collected) / len(errors_collected)
            if errors_collected else 0.0
        ),
        "avg_reward": (
            sum(rewards_collected) / len(rewards_collected)
            if rewards_collected else 0.0
        ),
        "max_error": max(errors_collected) if errors_collected else 0.0,
        "min_error": min(errors_collected) if errors_collected else 0.0,
        "max_reward": max(rewards_collected) if rewards_collected else 0.0,
        "min_reward": min(rewards_collected) if rewards_collected else 0.0,
        "memory_experiences": 0,
    }

    try:
        mem_health = await agent.memory.health_check()
        report["memory_experiences"] = mem_health["metrics"]["experience_count"]
    except Exception as exc:
        _log(f"获取记忆状态失败: {exc}")

    with open(_REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    _log("=" * 60)
    _log("六小时运行验证完成")
    _log(f"总运行时间: {elapsed_total/3600:.2f} 小时")
    _log(f"总周期数: {total_cycles}")
    _log(f"平均周期/小时: {report['cycles_per_hour']}")
    _log(f"执行任务数: {tasks_executed}")
    _log(f"异常次数: {crash_count}")
    _log(f"平均误差: {report['avg_error']:.4f}")
    _log(f"平均奖励: {report['avg_reward']:.4f}")
    _log(f"记忆经验数: {report['memory_experiences']}")
    _log("=" * 60)

    return report


if __name__ == "__main__":
    report = asyncio.run(run_agent(duration_seconds=_DURATION_SECONDS))
    print(json.dumps(report, indent=2, default=str))
