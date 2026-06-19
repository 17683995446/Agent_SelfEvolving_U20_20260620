"""
一小时长时间运行验证脚本。

启动Agent，记录所有日志到文件，每小时汇总报告。
"""

import asyncio
import json
import time
from pathlib import Path

from agent_core.common.di_container import reset_di_container
from agent_core.memory.agent_main import SelfEvolvingAgent

_LOG_FILE = Path("/workspace/logs/long_run.log")
_REPORT_FILE = Path("/workspace/logs/long_run_report.json")


def _log(msg: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


async def run_agent(duration_seconds: float = 3600.0) -> dict:
    """运行Agent指定时长并收集指标。"""
    reset_di_container()
    agent = SelfEvolvingAgent()

    config = {
        "perception": {},
        "drive_engine": {},
        "predictor": {"feature_dimensions": 10},
        "task_generator": {"exploration_rate": 0.3},
        "decision_engine": {"epsilon": 0.2},
        "memory": {"memory_capacity": 1000, "db_path": "long_run_memory.db"},
        "dashboard_port": 0,
    }

    _log("=" * 60)
    _log("开始一小时长时间运行验证")
    _log("=" * 60)

    await agent.initialize(config)
    _log("Agent初始化完成")

    health = await agent.health_check()
    _log(f"初始健康状态: {health['status']}")

    await agent.start(online_interval_seconds=1.0, offline_interval_seconds=30.0)
    _log("Agent双循环已启动 (在线1秒/周期, 离线30秒/周期)")

    start_time = time.time()
    cycle_count_start = agent._cycle_count
    errors_collected: list[float] = []
    rewards_collected: list[float] = []
    tasks_executed = 0

    while time.time() - start_time < duration_seconds:
        await asyncio.sleep(10.0)
        elapsed = time.time() - start_time
        cycles = agent._cycle_count - cycle_count_start
        errors_collected.extend(agent._recent_errors[-5:])
        rewards_collected.extend(agent._recent_rewards[-5:])

        if agent._current_task is not None:
            tasks_executed += 1

        _log(
            f"运行中... 已运行 {elapsed/60:.1f} 分钟, "
            f"周期数 {cycles}, 当前任务 {agent._current_task}"
        )

    _log("运行时间到达，准备停止...")
    await agent.stop()

    total_cycles = agent._cycle_count - cycle_count_start
    report = {
        "duration_seconds": duration_seconds,
        "total_cycles": total_cycles,
        "tasks_executed": tasks_executed,
        "final_health": health,
        "error_history_sample": errors_collected[-20:],
        "reward_history_sample": rewards_collected[-20:],
        "avg_error": sum(errors_collected) / len(errors_collected) if errors_collected else 0.0,
        "avg_reward": sum(rewards_collected) / len(rewards_collected) if rewards_collected else 0.0,
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
    _log("一小时运行验证完成")
    _log(f"总周期数: {total_cycles}")
    _log(f"执行任务数: {tasks_executed}")
    _log(f"平均误差: {report['avg_error']:.4f}")
    _log(f"平均奖励: {report['avg_reward']:.4f}")
    _log(f"记忆经验数: {report['memory_experiences']}")
    _log("=" * 60)

    return report


if __name__ == "__main__":
    report = asyncio.run(run_agent(duration_seconds=3600.0))
    print(json.dumps(report, indent=2, default=str))
