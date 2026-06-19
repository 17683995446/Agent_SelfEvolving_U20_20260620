"""
日志轮转与归档模块。

实现按文件大小和时间轮转的日志管理。

第一性原理：
- 日志文件无限增长会导致磁盘耗尽
- 轮转必须原子化，不丢失日志
- 归档压缩节省空间
"""

import gzip
import os
import shutil
from datetime import datetime
from typing import Optional

from agent_core.common.logger import get_logger


class LogRotator:
    """
    日志轮转器。

    按大小或时间轮转日志文件，支持压缩归档。
    """

    def __init__(
        self,
        log_path: str,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ) -> None:
        self._log_path = log_path
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._logger = get_logger()

    def should_rotate(self) -> bool:
        """
        检查是否需要轮转。

        Returns:
            文件超过最大大小时返回True。
        """
        if not os.path.exists(self._log_path):
            return False
        return os.path.getsize(self._log_path) >= self._max_bytes

    def rotate(self) -> bool:
        """
        执行日志轮转。

        Returns:
            成功返回True。
        """
        if not self.should_rotate():
            return True
        try:
            self._do_rotation()
            return True
        except OSError as exc:
            self._logger.error(f"[LogRotator] Rotation failed: {exc}")
            return False

    def _do_rotation(self) -> None:
        """执行轮转操作。"""
        self._remove_oldest()
        self._shift_backups()
        self._archive_current()

    def _remove_oldest(self) -> None:
        """删除最旧的备份。"""
        oldest = f"{self._log_path}.{self._backup_count}.gz"
        if os.path.exists(oldest):
            os.unlink(oldest)

    def _shift_backups(self) -> None:
        """移动备份文件编号。"""
        for i in range(self._backup_count - 1, 0, -1):
            src = f"{self._log_path}.{i}.gz"
            dst = f"{self._log_path}.{i + 1}.gz"
            if os.path.exists(src):
                shutil.move(src, dst)

    def _archive_current(self) -> None:
        """归档当前日志文件。"""
        if not os.path.exists(self._log_path):
            return
        archive = f"{self._log_path}.1.gz"
        with open(self._log_path, "rb") as f_in:
            with gzip.open(archive, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        with open(self._log_path, "w"):
            pass

    def get_archive_list(self) -> list:
        """
        获取归档文件列表。

        Returns:
            归档文件路径列表。
        """
        archives = []
        for i in range(1, self._backup_count + 1):
            path = f"{self._log_path}.{i}.gz"
            if os.path.exists(path):
                archives.append(path)
        return archives
