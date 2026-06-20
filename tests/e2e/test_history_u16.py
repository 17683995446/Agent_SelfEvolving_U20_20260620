"""
U-16: 命令历史持久化与搜索 测试。

覆盖：
- HistoryEntry: 历史条目
- HistoryManager: 历史管理器（记录/加载/保存/搜索/统计/清除）
- history CLI: list/search/stats/clear
- CLI集成: 命令执行后自动记录历史
"""

import argparse
import io
import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

from agent_core.history_cli import (
    HistoryEntry,
    HistoryManager,
    cmd_history_list,
    cmd_history_search,
    cmd_history_stats,
    cmd_history_clear,
    handle_history,
    add_history_subparser,
    _HISTORY_FILE,
    _DEFAULT_MAX_ENTRIES,
)
from agent_core.cli import main, _build_parser


class TestHistoryEntry(unittest.TestCase):
    """HistoryEntry测试。"""

    def test_create_with_defaults(self):
        """默认创建。"""
        entry = HistoryEntry(command="agent start")
        self.assertEqual(entry.command, "agent start")
        self.assertIsNotNone(entry.timestamp)
        self.assertIsNone(entry.exit_code)

    def test_create_with_params(self):
        """带参数创建。"""
        entry = HistoryEntry(
            command="agent status",
            timestamp=1000.0,
            exit_code=0,
        )
        self.assertEqual(entry.command, "agent status")
        self.assertEqual(entry.timestamp, 1000.0)
        self.assertEqual(entry.exit_code, 0)

    def test_to_dict(self):
        """转字典。"""
        entry = HistoryEntry(command="test", timestamp=1000.0, exit_code=0)
        d = entry.to_dict()
        self.assertEqual(d["command"], "test")
        self.assertEqual(d["timestamp"], 1000.0)
        self.assertEqual(d["exit_code"], 0)

    def test_from_dict(self):
        """从字典创建。"""
        d = {"command": "test", "timestamp": 1000.0, "exit_code": 1}
        entry = HistoryEntry.from_dict(d)
        self.assertEqual(entry.command, "test")
        self.assertEqual(entry.timestamp, 1000.0)
        self.assertEqual(entry.exit_code, 1)

    def test_roundtrip(self):
        """字典往返转换。"""
        original = HistoryEntry(command="roundtrip", timestamp=2000.0, exit_code=0)
        d = original.to_dict()
        restored = HistoryEntry.from_dict(d)
        self.assertEqual(restored.command, original.command)
        self.assertEqual(restored.timestamp, original.timestamp)
        self.assertEqual(restored.exit_code, original.exit_code)

    def test_format_time(self):
        """格式化时间。"""
        entry = HistoryEntry(command="test", timestamp=0)
        time_str = entry.format_time()
        self.assertIsInstance(time_str, str)
        self.assertIn("1970", time_str)  # timestamp=0 是1970年


class TestHistoryManager(unittest.TestCase):
    """HistoryManager测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manager = HistoryManager(project_dir=self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_initially(self):
        """初始为空。"""
        self.assertEqual(self.manager.count(), 0)
        self.assertEqual(self.manager.get_all(), [])

    def test_record(self):
        """记录命令。"""
        self.manager.record("agent start", exit_code=0)
        self.assertEqual(self.manager.count(), 1)
        entries = self.manager.get_all()
        self.assertEqual(entries[0].command, "agent start")
        self.assertEqual(entries[0].exit_code, 0)

    def test_record_persists_to_file(self):
        """记录持久化到文件。"""
        self.manager.record("agent version", exit_code=0)
        self.assertTrue(os.path.exists(self.manager.history_file_path))

    def test_record_loads_from_file(self):
        """从文件加载历史。"""
        self.manager.record("agent start", exit_code=0)
        self.manager.record("agent status", exit_code=0)

        manager2 = HistoryManager(project_dir=self.tmpdir)
        self.assertEqual(manager2.count(), 2)

    def test_record_empty_command_ignored(self):
        """空命令被忽略。"""
        self.manager.record("", exit_code=0)
        self.manager.record("   ", exit_code=0)
        self.assertEqual(self.manager.count(), 0)

    def test_record_history_command_ignored(self):
        """history命令自身不被记录。"""
        self.manager.record("history list", exit_code=0)
        self.assertEqual(self.manager.count(), 0)

    def test_record_exit_quit_ignored(self):
        """exit/quit不被记录。"""
        self.manager.record("exit", exit_code=0)
        self.manager.record("quit", exit_code=0)
        self.assertEqual(self.manager.count(), 0)

    def test_get_recent(self):
        """获取最近记录。"""
        for i in range(10):
            self.manager.record(f"cmd{i}", exit_code=0)
        recent = self.manager.get_recent(5)
        self.assertEqual(len(recent), 5)
        self.assertEqual(recent[-1].command, "cmd9")

    def test_get_recent_all_if_fewer(self):
        """记录少于请求数时返回全部。"""
        self.manager.record("cmd1", exit_code=0)
        recent = self.manager.get_recent(10)
        self.assertEqual(len(recent), 1)

    def test_get_recent_zero(self):
        """请求数为0返回空。"""
        self.manager.record("cmd1", exit_code=0)
        recent = self.manager.get_recent(0)
        self.assertEqual(recent, [])

    def test_search_keyword(self):
        """关键词搜索。"""
        self.manager.record("agent start --env prod", exit_code=0)
        self.manager.record("agent status", exit_code=0)
        self.manager.record("agent start --env dev", exit_code=0)

        results = self.manager.search("start")
        self.assertEqual(len(results), 2)

    def test_search_no_match(self):
        """无匹配返回空。"""
        self.manager.record("agent start", exit_code=0)
        results = self.manager.search("nonexistent")
        self.assertEqual(results, [])

    def test_search_ignore_case(self):
        """忽略大小写搜索。"""
        self.manager.record("agent START", exit_code=0)
        results = self.manager.search("start", ignore_case=True)
        self.assertEqual(len(results), 1)

    def test_search_case_sensitive(self):
        """区分大小写搜索。"""
        self.manager.record("agent START", exit_code=0)
        results = self.manager.search("start", ignore_case=False)
        self.assertEqual(results, [])

    def test_search_regex(self):
        """正则搜索。"""
        self.manager.record("agent start --env prod", exit_code=0)
        self.manager.record("agent start --env dev", exit_code=0)
        self.manager.record("agent status", exit_code=0)

        results = self.manager.search(r"start.*prod", use_regex=True)
        self.assertEqual(len(results), 1)

    def test_search_invalid_regex(self):
        """无效正则返回空。"""
        self.manager.record("agent start", exit_code=0)
        results = self.manager.search("[invalid", use_regex=True)
        self.assertEqual(results, [])

    def test_stats_empty(self):
        """空历史统计。"""
        stats = self.manager.stats()
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["unique_commands"], 0)
        self.assertIsNone(stats["time_range"])

    def test_stats_with_data(self):
        """有数据的统计。"""
        self.manager.record("agent start", exit_code=0)
        self.manager.record("agent start", exit_code=0)
        self.manager.record("agent status", exit_code=0)

        stats = self.manager.stats()
        self.assertEqual(stats["total"], 3)
        # unique_commands统计的是命令第一个词，都是"agent"
        self.assertEqual(stats["unique_commands"], 1)
        self.assertIsNotNone(stats["time_range"])

    def test_stats_top_commands(self):
        """统计最常用命令。"""
        self.manager.record("agent start", exit_code=0)
        self.manager.record("agent start", exit_code=0)
        self.manager.record("agent status", exit_code=0)

        stats = self.manager.stats()
        top = stats["top_commands"]
        self.assertGreater(len(top), 0)
        self.assertEqual(top[0]["command"], "agent")
        self.assertEqual(top[0]["count"], 3)

    def test_clear(self):
        """清除历史。"""
        self.manager.record("agent start", exit_code=0)
        self.assertTrue(self.manager.clear())
        self.assertEqual(self.manager.count(), 0)

    def test_clear_persists(self):
        """清除持久化。"""
        self.manager.record("agent start", exit_code=0)
        self.manager.clear()

        manager2 = HistoryManager(project_dir=self.tmpdir)
        self.assertEqual(manager2.count(), 0)

    def test_max_entries_limit(self):
        """容量限制。"""
        manager = HistoryManager(project_dir=self.tmpdir, max_entries=5)
        for i in range(10):
            manager.record(f"cmd{i}", exit_code=0)
        self.assertEqual(manager.count(), 5)
        # 应保留最后5条
        entries = manager.get_all()
        self.assertEqual(entries[0].command, "cmd5")
        self.assertEqual(entries[-1].command, "cmd9")

    def test_load_invalid_json(self):
        """加载无效JSON不报错。"""
        with open(self.manager.history_file_path, "w") as f:
            f.write("invalid json")
        manager2 = HistoryManager(project_dir=self.tmpdir)
        self.assertEqual(manager2.count(), 0)

    def test_history_file_path(self):
        """历史文件路径正确。"""
        expected = os.path.join(self.tmpdir, _HISTORY_FILE)
        self.assertEqual(self.manager.history_file_path, expected)


class TestCmdHistoryList(unittest.TestCase):
    """cmd_history_list测试。"""

    def test_empty_history(self):
        """空历史。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("agent_core.history_cli.HistoryManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_recent.return_value = []
                instance.count.return_value = 0
                with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                    args = MagicMock(limit=20)
                    result = cmd_history_list(args)
            self.assertEqual(result, 0)
            self.assertIn("No command history", mock_out.getvalue())

    def test_with_entries(self):
        """有记录。"""
        entry = HistoryEntry(command="agent start", timestamp=1000.0, exit_code=0)
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.history_cli.HistoryManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_recent.return_value = [entry]
                instance.count.return_value = 1
                args = MagicMock(limit=20)
                result = cmd_history_list(args)
        self.assertEqual(result, 0)

    def test_shows_exit_code(self):
        """显示退出码。"""
        entry = HistoryEntry(command="agent fail", timestamp=1000.0, exit_code=1)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("agent_core.history_cli.HistoryManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_recent.return_value = [entry]
                instance.count.return_value = 1
                args = MagicMock(limit=20)
                cmd_history_list(args)
        output = mock_out.getvalue()
        self.assertIn("exit:1", output)


class TestCmdHistorySearch(unittest.TestCase):
    """cmd_history_search测试。"""

    def test_no_matches(self):
        """无匹配。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.history_cli.HistoryManager") as MockMgr:
                instance = MockMgr.return_value
                instance.search.return_value = []
                args = MagicMock(pattern="test", regex=False, case_sensitive=False)
                result = cmd_history_search(args)
        self.assertEqual(result, 0)

    def test_with_matches(self):
        """有匹配。"""
        entry = HistoryEntry(command="agent start", timestamp=1000.0, exit_code=0)
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.history_cli.HistoryManager") as MockMgr:
                instance = MockMgr.return_value
                instance.search.return_value = [entry]
                args = MagicMock(pattern="start", regex=False, case_sensitive=False)
                result = cmd_history_search(args)
        self.assertEqual(result, 0)


class TestCmdHistoryStats(unittest.TestCase):
    """cmd_history_stats测试。"""

    def test_empty_stats(self):
        """空统计。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.history_cli.HistoryManager") as MockMgr:
                instance = MockMgr.return_value
                instance.stats.return_value = {
                    "total": 0, "unique_commands": 0,
                    "top_commands": [], "time_range": None
                }
                result = cmd_history_stats(MagicMock())
        self.assertEqual(result, 0)

    def test_with_stats(self):
        """有数据统计。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.history_cli.HistoryManager") as MockMgr:
                instance = MockMgr.return_value
                instance.stats.return_value = {
                    "total": 10, "unique_commands": 3,
                    "top_commands": [{"command": "start", "count": 5}],
                    "time_range": {"first": 1000.0, "last": 2000.0}
                }
                result = cmd_history_stats(MagicMock())
        self.assertEqual(result, 0)


class TestCmdHistoryClear(unittest.TestCase):
    """cmd_history_clear测试。"""

    def test_clear_success(self):
        """清除成功。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.history_cli.HistoryManager") as MockMgr:
                instance = MockMgr.return_value
                instance.clear.return_value = True
                result = cmd_history_clear(MagicMock())
        self.assertEqual(result, 0)

    def test_clear_failure(self):
        """清除失败。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.history_cli.HistoryManager") as MockMgr:
                instance = MockMgr.return_value
                instance.clear.return_value = False
                result = cmd_history_clear(MagicMock())
        self.assertEqual(result, 1)


class TestHandleHistory(unittest.TestCase):
    """handle_history测试。"""

    def test_none_action_lists(self):
        """None action执行list。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.history_cli.HistoryManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_recent.return_value = []
                instance.count.return_value = 0
                args = MagicMock(history_action=None, limit=20)
                result = handle_history(args)
        self.assertEqual(result, 0)

    def test_unknown_action(self):
        """未知action返回1。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            args = MagicMock(history_action="unknown")
            result = handle_history(args)
        self.assertEqual(result, 1)


class TestAddHistorySubparser(unittest.TestCase):
    """add_history_subparser测试。"""

    def test_history_subparser_registered(self):
        """history子命令已注册。"""
        parser = _build_parser()
        args = parser.parse_args(["history"])
        self.assertEqual(args.command, "history")

    def test_history_list(self):
        """history list。"""
        parser = _build_parser()
        args = parser.parse_args(["history", "list"])
        self.assertEqual(args.history_action, "list")

    def test_history_list_with_limit(self):
        """history list -n。"""
        parser = _build_parser()
        args = parser.parse_args(["history", "list", "-n", "50"])
        self.assertEqual(args.limit, 50)

    def test_history_search(self):
        """history search。"""
        parser = _build_parser()
        args = parser.parse_args(["history", "search", "start"])
        self.assertEqual(args.history_action, "search")
        self.assertEqual(args.pattern, "start")

    def test_history_search_regex(self):
        """history search --regex。"""
        parser = _build_parser()
        args = parser.parse_args(["history", "search", "start.*prod", "--regex"])
        self.assertTrue(args.regex)

    def test_history_search_case_sensitive(self):
        """history search --case-sensitive。"""
        parser = _build_parser()
        args = parser.parse_args(["history", "search", "Start", "--case-sensitive"])
        self.assertTrue(args.case_sensitive)

    def test_history_stats(self):
        """history stats。"""
        parser = _build_parser()
        args = parser.parse_args(["history", "stats"])
        self.assertEqual(args.history_action, "stats")

    def test_history_clear(self):
        """history clear。"""
        parser = _build_parser()
        args = parser.parse_args(["history", "clear"])
        self.assertEqual(args.history_action, "clear")


class TestCLIIntegration(unittest.TestCase):
    """CLI集成测试。"""

    def test_history_list_via_main(self):
        """agent history list通过main。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    result = main(["history", "list"])
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)

    def test_history_stats_via_main(self):
        """agent history stats通过main。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    result = main(["history", "stats"])
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)

    def test_command_recorded_to_history(self):
        """命令执行后记录到历史。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    main(["version"])
                # 验证历史文件已创建
                history_path = os.path.join(tmpdir, _HISTORY_FILE)
                self.assertTrue(os.path.exists(history_path))
                with open(history_path, "r") as f:
                    data = json.load(f)
                self.assertGreater(len(data["entries"]), 0)
                self.assertEqual(data["entries"][0]["command"], "version")
            finally:
                os.chdir(old_cwd)

    def test_history_in_handlers(self):
        """history在handlers中。"""
        parser = _build_parser()
        args = parser.parse_args(["history"])
        self.assertEqual(args.command, "history")


class TestEdgeCases(unittest.TestCase):
    """边界情况测试。"""

    def test_persistence_across_managers(self):
        """跨管理器持久化。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager1 = HistoryManager(project_dir=tmpdir)
            manager1.record("cmd1", exit_code=0)
            manager1.record("cmd2", exit_code=1)

            manager2 = HistoryManager(project_dir=tmpdir)
            self.assertEqual(manager2.count(), 2)
            entries = manager2.get_all()
            self.assertEqual(entries[0].command, "cmd1")
            self.assertEqual(entries[0].exit_code, 0)
            self.assertEqual(entries[1].command, "cmd2")
            self.assertEqual(entries[1].exit_code, 1)

    def test_search_empty_pattern(self):
        """空模式搜索。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = HistoryManager(project_dir=tmpdir)
            manager.record("agent start", exit_code=0)
            results = manager.search("")
            # 空字符串匹配所有
            self.assertEqual(len(results), 1)

    def test_stats_time_range(self):
        """统计时间范围。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = HistoryManager(project_dir=tmpdir)
            manager.record("cmd1", exit_code=0)
            time.sleep(0.01)
            manager.record("cmd2", exit_code=0)

            stats = manager.stats()
            time_range = stats["time_range"]
            self.assertLess(time_range["first"], time_range["last"])

    def test_default_max_entries(self):
        """默认最大记录数。"""
        self.assertEqual(_DEFAULT_MAX_ENTRIES, 1000)


if __name__ == "__main__":
    unittest.main()
