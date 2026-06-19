"""
日志轮转与归档模块测试。

覆盖：轮转触发、归档生成、备份移位、旧备份删除、列表获取。
"""

import gzip
import os
import tempfile

import pytest

from agent_core.common.log_rotator import LogRotator


class TestLogRotator:
    """LogRotator测试类。"""

    @pytest.fixture
    def rotator(self):
        """创建轮转器实例。"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            path = f.name
        rotator = LogRotator(path, max_bytes=10, backup_count=3)
        rotator._log_path = path
        yield rotator
        for i in range(1, 4):
            archive = f"{path}.{i}.gz"
            if os.path.exists(archive):
                os.unlink(archive)
        if os.path.exists(path):
            os.unlink(path)

    def test_should_rotate_false(self, rotator):
        """测试小文件不轮转。"""
        assert rotator.should_rotate() is False

    def test_should_rotate_true(self, rotator):
        """测试大文件需要轮转。"""
        with open(rotator._log_path, "w") as f:
            f.write("x" * 20)
        assert rotator.should_rotate() is True

    def test_rotate_creates_archive(self, rotator):
        """测试轮转生成归档。"""
        with open(rotator._log_path, "w") as f:
            f.write("log content")
        result = rotator.rotate()
        assert result is True
        assert os.path.exists(f"{rotator._log_path}.1.gz")
        with gzip.open(f"{rotator._log_path}.1.gz", "rt") as f:
            assert f.read() == "log content"

    def test_rotate_shifts_backups(self, rotator):
        """测试备份编号移位。"""
        with open(rotator._log_path, "w") as f:
            f.write("first content long enough")
        rotator.rotate()
        with open(rotator._log_path, "w") as f:
            f.write("second content long enough")
        rotator.rotate()
        assert os.path.exists(f"{rotator._log_path}.1.gz")
        assert os.path.exists(f"{rotator._log_path}.2.gz")

    def test_rotate_removes_oldest(self, rotator):
        """测试超出备份数时删除最旧。"""
        for i in range(5):
            with open(rotator._log_path, "w") as f:
                f.write(f"log content {i} long enough for rotation")
            rotator.rotate()
        assert not os.path.exists(f"{rotator._log_path}.4.gz")
        assert os.path.exists(f"{rotator._log_path}.3.gz")

    def test_get_archive_list(self, rotator):
        """测试获取归档列表。"""
        with open(rotator._log_path, "w") as f:
            f.write("log content long enough")
        rotator.rotate()
        archives = rotator.get_archive_list()
        assert len(archives) == 1
