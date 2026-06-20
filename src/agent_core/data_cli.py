"""
数据导出/导入CLI模块。

将PersistenceManager的数据管理能力暴露到CLI，用户可以：
- 导出经验数据为JSON（备份/迁移）
- 导入经验数据（恢复/迁移）
- 查看数据统计

第一性原理：
- 数据是Agent的"记忆"，用户需要便捷工具备份和迁移
- 导出/导入能力基于已有的PersistenceManager，只需暴露入口
- 进度指示器让长时间操作有反馈
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_core.common.logger import get_logger
from agent_core.progress import ProgressBar, show_progress

# 默认数据库路径
_DEFAULT_DB_PATH = "agent_memory.db"

# 颜色
_COLOR_RESET = "\033[0m"
_COLOR_RED = "\033[31m"
_COLOR_GREEN = "\033[32m"
_COLOR_YELLOW = "\033[33m"
_COLOR_CYAN = "\033[36m"
_COLOR_BOLD = "\033[1m"
_COLOR_BLUE = "\033[34m"
_COLOR_MAGENTA = "\033[35m"

_COLOR_ENABLED = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False


def _colorize(text: str, color: str) -> str:
    """添加颜色（非TTY环境不添加）。"""
    if not _COLOR_ENABLED:
        return text
    return f"{color}{text}{_COLOR_RESET}"


def _print_error(msg: str) -> None:
    """打印错误信息。"""
    print(f"{_colorize('[ERROR]', _COLOR_RED)} {msg}", file=sys.stderr)


def _print_info(msg: str) -> None:
    """打印信息。"""
    print(f"{_colorize('[INFO]', _COLOR_BLUE)} {msg}")


def _print_success(msg: str) -> None:
    """打印成功信息。"""
    print(f"{_colorize('[OK]', _COLOR_GREEN)} {msg}")


def _print_warning(msg: str) -> None:
    """打印警告信息。"""
    print(f"{_colorize('[WARN]', _COLOR_YELLOW)} {msg}")


def _resolve_db_path(db_arg: Optional[str]) -> Optional[str]:
    """
    解析数据库路径。

    优先级：--db参数 > 默认路径 > None
    """
    if db_arg:
        if os.path.exists(db_arg):
            return db_arg
        _print_error(f"Database not found: {db_arg}")
        return None

    if os.path.exists(_DEFAULT_DB_PATH):
        return _DEFAULT_DB_PATH

    _print_error(
        f"No database found. Specify with --db <path>. "
        f"Default: {_DEFAULT_DB_PATH}"
    )
    return None


def _get_table_count(conn: sqlite3.Connection, table: str) -> int:
    """获取表行数。"""
    try:
        cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
        return cursor.fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def cmd_data_export(args) -> int:
    """
    导出经验数据为JSON。

    将SQLite中的经验数据导出为可读的JSON文件。
    """
    db_path = _resolve_db_path(getattr(args, "db", None))
    if db_path is None:
        return 1

    output = getattr(args, "output", None)
    if not output:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output = f"agent_export_{timestamp}.json"

    limit = getattr(args, "limit", 0)  # 0 = 全部

    _print_info(f"Exporting from: {db_path}")

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # 检查表是否存在
        total = _get_table_count(conn, "experiences")
        if total == 0:
            _print_warning("No experiences found in database")
            conn.close()
            return 0

        export_count = min(total, limit) if limit > 0 else total
        _print_info(f"Found {total} experiences, exporting {export_count}")

        # 查询数据
        if limit > 0:
            cursor = conn.execute(
                "SELECT * FROM experiences ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM experiences ORDER BY timestamp DESC"
            )

        rows = cursor.fetchall()

        # 进度条
        with show_progress(
            total=len(rows),
            description="Exporting",
            enabled=_COLOR_ENABLED,
        ) as bar:
            experiences = []
            for i, row in enumerate(rows):
                exp_data = {}
                for key in row.keys():
                    value = row[key]
                    # 尝试解析JSON字段
                    if isinstance(value, str) and value.startswith("{"):
                        try:
                            exp_data[key] = json.loads(value)
                        except json.JSONDecodeError:
                            exp_data[key] = value
                    else:
                        exp_data[key] = value
                experiences.append(exp_data)
                bar.increment()

        # 导出配置快照
        config_snapshots = []
        try:
            cursor = conn.execute(
                "SELECT * FROM config_snapshots ORDER BY timestamp DESC"
            )
            for row in cursor.fetchall():
                config_snapshots.append({
                    "timestamp": row["timestamp"],
                    "config": json.loads(row["config"]),
                })
        except sqlite3.OperationalError:
            pass

        # 导出运行时状态
        runtime_state = {}
        try:
            cursor = conn.execute("SELECT key, value FROM runtime_state")
            for row in cursor.fetchall():
                runtime_state[row["key"]] = json.loads(row["value"])
        except sqlite3.OperationalError:
            pass

        # 构建导出数据
        export_data = {
            "metadata": {
                "export_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "export_timestamp": time.time(),
                "source_db": db_path,
                "experience_count": len(experiences),
                "config_snapshot_count": len(config_snapshots),
                "runtime_state_keys": len(runtime_state),
            },
            "experiences": experiences,
            "config_snapshots": config_snapshots,
            "runtime_state": runtime_state,
        }

        # 写入文件
        with open(output, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)

        conn.close()

        file_size = os.path.getsize(output)
        _print_success(f"Exported {len(experiences)} experiences to {output}")
        _print_info(f"  File size: {file_size:,} bytes")
        _print_info(f"  Config snapshots: {len(config_snapshots)}")
        _print_info(f"  Runtime state keys: {len(runtime_state)}")

        return 0

    except sqlite3.Error as exc:
        _print_error(f"Database error: {exc}")
        return 1
    except OSError as exc:
        _print_error(f"File error: {exc}")
        return 1


def cmd_data_import(args) -> int:
    """
    导入经验数据。

    从JSON文件导入经验数据到SQLite数据库。
    """
    input_file = getattr(args, "input", None)
    if not input_file:
        _print_error("Input file is required (--input <path>)")
        return 1

    if not os.path.isfile(input_file):
        _print_error(f"Input file not found: {input_file}")
        return 1

    db_path = getattr(args, "db", _DEFAULT_DB_PATH)
    merge = getattr(args, "merge", False)

    _print_info(f"Importing from: {input_file}")
    _print_info(f"Target database: {db_path}")

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        _print_error(f"Invalid JSON: {exc}")
        return 1
    except OSError as exc:
        _print_error(f"Failed to read file: {exc}")
        return 1

    experiences = data.get("experiences", [])
    if not experiences:
        _print_warning("No experiences found in import file")
        return 0

    _print_info(f"Found {len(experiences)} experiences to import")

    try:
        conn = sqlite3.connect(str(db_path))

        # 确保表存在
        conn.execute("""
            CREATE TABLE IF NOT EXISTS experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                feature_vector TEXT NOT NULL,
                raw_sensors TEXT NOT NULL,
                prediction TEXT NOT NULL,
                drives TEXT NOT NULL,
                task TEXT,
                result TEXT NOT NULL,
                error TEXT NOT NULL,
                priority REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS config_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                config TEXT NOT NULL
            )
        """)

        # 非合并模式：清空现有数据
        if not merge:
            _print_info("Non-merge mode: clearing existing experiences")
            conn.execute("DELETE FROM experiences")

        # 导入经验数据
        with show_progress(
            total=len(experiences),
            description="Importing",
            enabled=_COLOR_ENABLED,
        ) as bar:
            for exp in experiences:
                # 将嵌套对象转回JSON字符串
                row = (
                    exp.get("timestamp", time.time()),
                    json.dumps(exp.get("feature_vector", "[]"))
                        if isinstance(exp.get("feature_vector"), (list, dict))
                        else exp.get("feature_vector", "[]"),
                    json.dumps(exp.get("raw_sensors", {}))
                        if isinstance(exp.get("raw_sensors"), (list, dict))
                        else exp.get("raw_sensors", "{}"),
                    json.dumps(exp.get("prediction", {}))
                        if isinstance(exp.get("prediction"), (list, dict))
                        else exp.get("prediction", "{}"),
                    json.dumps(exp.get("drives", {}))
                        if isinstance(exp.get("drives"), (list, dict))
                        else exp.get("drives", "{}"),
                    json.dumps(exp.get("task"))
                        if exp.get("task") is not None
                        else None,
                    json.dumps(exp.get("result", {}))
                        if isinstance(exp.get("result"), (list, dict))
                        else exp.get("result", "{}"),
                    json.dumps(exp.get("error", {}))
                        if isinstance(exp.get("error"), (list, dict))
                        else exp.get("error", "{}"),
                    exp.get("priority", 0.0),
                )
                conn.execute("""
                    INSERT INTO experiences
                    (timestamp, feature_vector, raw_sensors, prediction,
                     drives, task, result, error, priority)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, row)
                bar.increment()

        # 导入配置快照
        config_snapshots = data.get("config_snapshots", [])
        for snap in config_snapshots:
            conn.execute(
                "INSERT INTO config_snapshots (timestamp, config) VALUES (?, ?)",
                (snap.get("timestamp", time.time()),
                 json.dumps(snap.get("config", {}))),
            )

        conn.commit()

        # 统计结果
        total = _get_table_count(conn, "experiences")
        conn.close()

        _print_success(f"Imported {len(experiences)} experiences")
        _print_info(f"  Total experiences in database: {total}")
        _print_info(f"  Config snapshots imported: {len(config_snapshots)}")

        return 0

    except sqlite3.Error as exc:
        _print_error(f"Database error: {exc}")
        return 1
    except OSError as exc:
        _print_error(f"File error: {exc}")
        return 1


def cmd_data_stats(args) -> int:
    """
    显示数据统计。

    显示数据库中的经验数、配置快照数、运行时状态数等。
    """
    db_path = _resolve_db_path(getattr(args, "db", None))
    if db_path is None:
        return 1

    try:
        conn = sqlite3.connect(str(db_path))

        print(_colorize("=== Data Statistics ===", _COLOR_BOLD))
        print(f"  Database: {db_path}")
        print(f"  File Size: {os.path.getsize(db_path):,} bytes")
        print()

        # 经验统计
        exp_count = _get_table_count(conn, "experiences")
        print(_colorize("--- Experiences ---", _COLOR_CYAN))
        print(f"  Total: {exp_count}")

        if exp_count > 0:
            cursor = conn.execute(
                "SELECT MIN(timestamp), MAX(timestamp) FROM experiences"
            )
            min_ts, max_ts = cursor.fetchone()
            if min_ts and max_ts:
                print(f"  Earliest: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(min_ts))}")
                print(f"  Latest:   {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(max_ts))}")

            cursor = conn.execute(
                "SELECT AVG(priority), MIN(priority), MAX(priority) FROM experiences"
            )
            avg_pri, min_pri, max_pri = cursor.fetchone()
            if avg_pri is not None:
                print(f"  Priority: avg={avg_pri:.3f}, min={min_pri:.3f}, max={max_pri:.3f}")

        print()

        # 配置快照统计
        config_count = _get_table_count(conn, "config_snapshots")
        print(_colorize("--- Config Snapshots ---", _COLOR_CYAN))
        print(f"  Total: {config_count}")
        print()

        # 运行时状态统计
        runtime_count = _get_table_count(conn, "runtime_state")
        print(_colorize("--- Runtime State ---", _COLOR_CYAN))
        print(f"  Keys: {runtime_count}")

        if runtime_count > 0:
            cursor = conn.execute("SELECT key FROM runtime_state")
            keys = [row[0] for row in cursor.fetchall()]
            print(f"  Keys List: {', '.join(keys[:10])}")
            if len(keys) > 10:
                print(f"    ... and {len(keys) - 10} more")

        conn.close()
        return 0

    except sqlite3.Error as exc:
        _print_error(f"Database error: {exc}")
        return 1


def add_data_subparser(subparsers) -> None:
    """
    注册data子命令组到CLI解析器。

    Args:
        subparsers: argparse子命令解析器组。
    """
    data_parser = subparsers.add_parser(
        "data",
        help="数据管理（导出/导入/统计）",
        description="数据管理工具：导出经验、导入经验、查看统计",
    )
    data_sub = data_parser.add_subparsers(dest="data_action")

    # data export
    export_parser = data_sub.add_parser(
        "export", help="导出经验数据为JSON"
    )
    export_parser.add_argument(
        "--output", "-o", default=None,
        help="输出文件路径（默认: agent_export_<timestamp>.json）"
    )
    export_parser.add_argument(
        "--db", default=None,
        help=f"数据库路径（默认: {_DEFAULT_DB_PATH}）"
    )
    export_parser.add_argument(
        "--limit", type=int, default=0,
        help="导出条数限制（0=全部）"
    )

    # data import
    import_parser = data_sub.add_parser(
        "import", help="导入经验数据"
    )
    import_parser.add_argument(
        "input", help="输入文件路径（JSON）"
    )
    import_parser.add_argument(
        "--db", default=_DEFAULT_DB_PATH,
        help=f"目标数据库路径（默认: {_DEFAULT_DB_PATH}）"
    )
    import_parser.add_argument(
        "--merge", action="store_true",
        help="合并模式（不清空现有数据）"
    )

    # data stats
    stats_parser = data_sub.add_parser(
        "stats", help="显示数据统计"
    )
    stats_parser.add_argument(
        "--db", default=None,
        help=f"数据库路径（默认: {_DEFAULT_DB_PATH}）"
    )


def handle_data(args) -> int:
    """
    处理data子命令分发。

    Args:
        args: 解析后的命令行参数。

    Returns:
        退出码。
    """
    action = getattr(args, "data_action", None)

    if action is None:
        _print_info("Use 'agent data export/import/stats' to manage data")
        return 0
    elif action == "export":
        return cmd_data_export(args)
    elif action == "import":
        return cmd_data_import(args)
    elif action == "stats":
        return cmd_data_stats(args)
    else:
        _print_error(f"Unknown data action: {action}")
        return 1
