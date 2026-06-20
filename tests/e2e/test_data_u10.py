"""
U-10: 数据导出/导入 + 进度指示器 测试。

覆盖：data export/import/stats、进度指示器、错误处理、Shell集成。
"""

import io
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from agent_core.cli import main, _build_parser
from agent_core.data_cli import (
    handle_data,
    cmd_data_export,
    cmd_data_import,
    cmd_data_stats,
    _resolve_db_path,
    _get_table_count,
    add_data_subparser,
)
from agent_core.progress import ProgressBar, Spinner, ProgressContext, show_progress


class TestDataCLIParser(unittest.TestCase):
    """data子命令解析测试。"""

    def test_data_command_parsed(self):
        """data命令解析。"""
        parser = _build_parser()
        args = parser.parse_args(["data"])
        self.assertEqual(args.command, "data")

    def test_data_export_parsed(self):
        """data export解析。"""
        parser = _build_parser()
        args = parser.parse_args(["data", "export"])
        self.assertEqual(args.data_action, "export")

    def test_data_export_with_output(self):
        """data export带输出路径。"""
        parser = _build_parser()
        args = parser.parse_args(["data", "export", "--output", "/tmp/out.json"])
        self.assertEqual(args.output, "/tmp/out.json")

    def test_data_export_with_db(self):
        """data export带数据库路径。"""
        parser = _build_parser()
        args = parser.parse_args(["data", "export", "--db", "/tmp/test.db"])
        self.assertEqual(args.db, "/tmp/test.db")

    def test_data_export_with_limit(self):
        """data export带限制。"""
        parser = _build_parser()
        args = parser.parse_args(["data", "export", "--limit", "100"])
        self.assertEqual(args.limit, 100)

    def test_data_import_parsed(self):
        """data import解析。"""
        parser = _build_parser()
        args = parser.parse_args(["data", "import", "input.json"])
        self.assertEqual(args.data_action, "import")
        self.assertEqual(args.input, "input.json")

    def test_data_import_with_merge(self):
        """data import --merge。"""
        parser = _build_parser()
        args = parser.parse_args(["data", "import", "input.json", "--merge"])
        self.assertTrue(args.merge)

    def test_data_stats_parsed(self):
        """data stats解析。"""
        parser = _build_parser()
        args = parser.parse_args(["data", "stats"])
        self.assertEqual(args.data_action, "stats")

    def test_data_import_requires_input(self):
        """data import必须有input。"""
        parser = _build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["data", "import"])


class TestResolveDbPath(unittest.TestCase):
    """数据库路径解析测试。"""

    def test_explicit_db_exists(self):
        """显式指定存在的数据库。"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            result = _resolve_db_path(path)
            self.assertEqual(result, path)
        finally:
            os.unlink(path)

    def test_explicit_db_not_exists(self):
        """显式指定不存在的数据库。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            result = _resolve_db_path("/nonexistent.db")
        self.assertIsNone(result)

    def test_none_arg_no_default_db(self):
        """无参数且无默认数据库。"""
        with patch("agent_core.data_cli._DEFAULT_DB_PATH", "/nonexistent_default.db"):
            with patch("sys.stderr", new_callable=io.StringIO):
                result = _resolve_db_path(None)
        self.assertIsNone(result)


class TestGetTableCount(unittest.TestCase):
    """_get_table_count测试。"""

    def test_existing_table(self):
        """存在的表。"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE test (id INTEGER)")
            conn.execute("INSERT INTO test VALUES (1), (2), (3)")
            conn.commit()
            count = _get_table_count(conn, "test")
            self.assertEqual(count, 3)
            conn.close()
        finally:
            os.unlink(path)

    def test_nonexistent_table(self):
        """不存在的表返回0。"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            conn = sqlite3.connect(path)
            count = _get_table_count(conn, "nonexistent")
            self.assertEqual(count, 0)
            conn.close()
        finally:
            os.unlink(path)


def _create_test_db(db_path, exp_count=5):
    """创建测试数据库。"""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE experiences (
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
        CREATE TABLE config_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            config TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE runtime_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
    """)

    import time
    for i in range(exp_count):
        conn.execute("""
            INSERT INTO experiences
            (timestamp, feature_vector, raw_sensors, prediction,
             drives, task, result, error, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            time.time() + i,
            json.dumps([1.0, 2.0, 3.0]),
            json.dumps({"sensor": i}),
            json.dumps({"confidence": 0.9}),
            json.dumps({"safety": 0.5}),
            None,
            json.dumps({"success": True}),
            json.dumps({"mse": 0.1}),
            float(i) / exp_count,
        ))

    conn.execute(
        "INSERT INTO config_snapshots (timestamp, config) VALUES (?, ?)",
        (time.time(), json.dumps({"app_name": "test"}))
    )
    conn.execute(
        "INSERT INTO runtime_state (key, value, updated_at) VALUES (?, ?, ?)",
        ("state_key", json.dumps({"running": True}), time.time())
    )
    conn.commit()
    conn.close()


class TestDataExport(unittest.TestCase):
    """data export命令测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        _create_test_db(self.db_path, exp_count=5)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_export_basic(self):
        """基本导出。"""
        output_file = os.path.join(self.tmpdir, "export.json")
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                db=self.db_path,
                output=output_file,
                limit=0,
            )
            result = cmd_data_export(args)
        self.assertEqual(result, 0)
        self.assertTrue(os.path.exists(output_file))

        # 验证导出内容
        with open(output_file, "r") as f:
            data = json.load(f)
        self.assertIn("metadata", data)
        self.assertIn("experiences", data)
        self.assertEqual(len(data["experiences"]), 5)
        self.assertEqual(data["metadata"]["experience_count"], 5)

    def test_export_with_limit(self):
        """带限制导出。"""
        output_file = os.path.join(self.tmpdir, "export_limit.json")
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                db=self.db_path,
                output=output_file,
                limit=2,
            )
            result = cmd_data_export(args)
        self.assertEqual(result, 0)
        with open(output_file, "r") as f:
            data = json.load(f)
        self.assertEqual(len(data["experiences"]), 2)

    def test_export_default_output(self):
        """默认输出路径。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            args = MagicMock(
                db=self.db_path,
                output=None,
                limit=0,
            )
            result = cmd_data_export(args)
        self.assertEqual(result, 0)
        # 查找生成的文件
        exports = [f for f in os.listdir(".") if f.startswith("agent_export_")]
        if exports:
            for f in exports:
                os.unlink(f)

    def test_export_db_not_found(self):
        """数据库不存在。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(
                db="/nonexistent.db",
                output=None,
                limit=0,
            )
            result = cmd_data_export(args)
        self.assertEqual(result, 1)

    def test_export_empty_db(self):
        """空数据库导出。"""
        empty_db = os.path.join(self.tmpdir, "empty.db")
        conn = sqlite3.connect(empty_db)
        conn.execute("""
            CREATE TABLE experiences (
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
        conn.commit()
        conn.close()

        with patch("sys.stdout", new_callable=io.StringIO):
            args = MagicMock(
                db=empty_db,
                output=None,
                limit=0,
            )
            result = cmd_data_export(args)
        self.assertEqual(result, 0)


class TestDataImport(unittest.TestCase):
    """data import命令测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # 创建导出文件
        self.export_file = os.path.join(self.tmpdir, "export.json")
        self.source_db = os.path.join(self.tmpdir, "source.db")
        _create_test_db(self.source_db, exp_count=3)

        # 导出数据
        with patch("sys.stdout", new_callable=io.StringIO):
            args = MagicMock(
                db=self.source_db,
                output=self.export_file,
                limit=0,
            )
            cmd_data_export(args)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_import_basic(self):
        """基本导入。"""
        target_db = os.path.join(self.tmpdir, "target.db")
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                input=self.export_file,
                db=target_db,
                merge=False,
            )
            result = cmd_data_import(args)
        self.assertEqual(result, 0)
        self.assertTrue(os.path.exists(target_db))

        # 验证导入数据
        conn = sqlite3.connect(target_db)
        count = _get_table_count(conn, "experiences")
        self.assertEqual(count, 3)
        conn.close()

    def test_import_merge_mode(self):
        """合并模式导入。"""
        target_db = os.path.join(self.tmpdir, "target_merge.db")
        # 先创建有1条数据的数据库
        _create_test_db(target_db, exp_count=1)

        with patch("sys.stdout", new_callable=io.StringIO):
            args = MagicMock(
                input=self.export_file,
                db=target_db,
                merge=True,
            )
            result = cmd_data_import(args)
        self.assertEqual(result, 0)

        # 验证合并后数据（1 + 3 = 4）
        conn = sqlite3.connect(target_db)
        count = _get_table_count(conn, "experiences")
        self.assertEqual(count, 4)
        conn.close()

    def test_import_non_merge_mode(self):
        """非合并模式导入（清空后导入）。"""
        target_db = os.path.join(self.tmpdir, "target_nonmerge.db")
        # 先创建有5条数据的数据库
        _create_test_db(target_db, exp_count=5)

        with patch("sys.stdout", new_callable=io.StringIO):
            args = MagicMock(
                input=self.export_file,
                db=target_db,
                merge=False,
            )
            result = cmd_data_import(args)
        self.assertEqual(result, 0)

        # 验证清空后导入（3条）
        conn = sqlite3.connect(target_db)
        count = _get_table_count(conn, "experiences")
        self.assertEqual(count, 3)
        conn.close()

    def test_import_file_not_found(self):
        """文件不存在。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(
                input="/nonexistent.json",
                db=os.path.join(self.tmpdir, "target.db"),
                merge=False,
            )
            result = cmd_data_import(args)
        self.assertEqual(result, 1)

    def test_import_invalid_json(self):
        """无效JSON。"""
        invalid_file = os.path.join(self.tmpdir, "invalid.json")
        with open(invalid_file, "w") as f:
            f.write("{invalid json")

        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(
                input=invalid_file,
                db=os.path.join(self.tmpdir, "target.db"),
                merge=False,
            )
            result = cmd_data_import(args)
        self.assertEqual(result, 1)


class TestDataStats(unittest.TestCase):
    """data stats命令测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        _create_test_db(self.db_path, exp_count=5)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_stats_basic(self):
        """基本统计。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(db=self.db_path)
            result = cmd_data_stats(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Data Statistics", output)
        self.assertIn("Experiences", output)
        self.assertIn("Total: 5", output)
        self.assertIn("Config Snapshots", output)
        self.assertIn("Runtime State", output)

    def test_stats_db_not_found(self):
        """数据库不存在。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(db="/nonexistent.db")
            result = cmd_data_stats(args)
        self.assertEqual(result, 1)


class TestDataHandleDispatch(unittest.TestCase):
    """handle_data分发测试。"""

    def test_handle_none_action(self):
        """无action时显示提示。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(data_action=None)
            result = handle_data(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("data", output)

    def test_handle_unknown_action(self):
        """未知action。"""
        args = MagicMock(data_action="unknown")
        with patch("sys.stderr", new_callable=io.StringIO):
            result = handle_data(args)
        self.assertEqual(result, 1)


class TestDataCLIIntegration(unittest.TestCase):
    """CLI集成测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        _create_test_db(self.db_path, exp_count=3)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cli_export_via_main(self):
        """通过main调用data export。"""
        output_file = os.path.join(self.tmpdir, "cli_export.json")
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = main([
                "data", "export",
                "--db", self.db_path,
                "--output", output_file,
            ])
        self.assertEqual(result, 0)
        self.assertTrue(os.path.exists(output_file))

    def test_cli_stats_via_main(self):
        """通过main调用data stats。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = main(["data", "stats", "--db", self.db_path])
        self.assertEqual(result, 0)
        self.assertIn("Data Statistics", mock_stdout.getvalue())

    def test_cli_import_via_main(self):
        """通过main调用data import。"""
        # 先导出
        export_file = os.path.join(self.tmpdir, "import_test.json")
        with patch("sys.stdout", new_callable=io.StringIO):
            main(["data", "export", "--db", self.db_path, "--output", export_file])

        # 导入到新数据库
        target_db = os.path.join(self.tmpdir, "import_target.db")
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = main(["data", "import", export_file, "--db", target_db])
        self.assertEqual(result, 0)
        self.assertTrue(os.path.exists(target_db))


class TestProgressBar(unittest.TestCase):
    """ProgressBar测试。"""

    def test_progress_bar_disabled(self):
        """禁用时不输出。"""
        bar = ProgressBar(total=10, enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            bar.update(5)
            bar.finish()
        # 禁用时不应有输出
        self.assertEqual(mock_stdout.getvalue(), "")

    def test_progress_bar_update(self):
        """更新进度。"""
        bar = ProgressBar(total=10, enabled=False)
        bar.update(5)
        self.assertEqual(bar._current, 5)

    def test_progress_bar_increment(self):
        """增加进度。"""
        bar = ProgressBar(total=10, enabled=False)
        bar.increment(3)
        self.assertEqual(bar._current, 3)

    def test_progress_bar_finish(self):
        """完成进度。"""
        bar = ProgressBar(total=10, enabled=False)
        bar.finish()
        self.assertEqual(bar._current, 10)

    def test_progress_bar_max_total(self):
        """进度不超过总量。"""
        bar = ProgressBar(total=5, enabled=False)
        bar.update(100)
        self.assertEqual(bar._current, 5)


class TestProgressContext(unittest.TestCase):
    """ProgressContext测试。"""

    def test_context_manager(self):
        """上下文管理器。"""
        with ProgressContext(total=5, enabled=False) as bar:
            for i in range(5):
                bar.increment()
        self.assertEqual(bar._current, 5)

    def test_show_progress_function(self):
        """show_progress函数。"""
        with show_progress(total=3, enabled=False) as bar:
            bar.update(2)
        self.assertEqual(bar._current, 3)  # finish后为3


class TestSpinner(unittest.TestCase):
    """Spinner测试。"""

    def test_spinner_disabled(self):
        """禁用时不输出。"""
        spinner = Spinner(description="Loading", enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            spinner.start()
            spinner.stop()
        self.assertEqual(mock_stdout.getvalue(), "")

    def test_spinner_stop_with_message(self):
        """停止时显示消息。"""
        spinner = Spinner(description="Loading", enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            spinner.stop("Done!")
        self.assertIn("Done!", mock_stdout.getvalue())


class TestShellDataCommand(unittest.TestCase):
    """Shell data命令测试。"""

    def test_shell_data_help(self):
        """Shell data命令有帮助。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell(port=19999)
        self.assertTrue(hasattr(shell, "do_data"))
        doc = shell.do_data.__doc__
        self.assertIsNotNone(doc)
        self.assertIn("data", doc.lower())

    def test_shell_data_stats(self):
        """Shell data stats执行。"""
        from agent_core.interactive_shell import AgentShell
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            _create_test_db(db_path, exp_count=2)

            shell = AgentShell(port=19999)
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                shell.do_data(f"stats --db {db_path}")
            output = mock_stdout.getvalue()
            self.assertIn("Data Statistics", output)

    def test_shell_help_includes_data(self):
        """Shell帮助包含data。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell(port=19999)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            shell.do_help("")
        output = mock_stdout.getvalue()
        self.assertIn("Data", output)
        self.assertIn("data", output)


if __name__ == "__main__":
    unittest.main()
