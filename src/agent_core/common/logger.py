"""
日志模块。

全局固定日志格式与级别，禁止自定义。
支持JSON结构化输出。
"""

import json
import logging
import sys
from typing import Any

from .constants import LogLevel


class JsonFormatter(logging.Formatter):
    """JSON结构化日志格式化器。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class AgentLogger:
    """
    Agent日志器。

    单例模式，全局统一日志格式。
    """

    _instance: "AgentLogger" = None  # type: ignore[assignment]

    def __new__(cls) -> "AgentLogger":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup()
        return cls._instance

    def _setup(self) -> None:
        self._logger = logging.getLogger("self_evolving_agent")
        self._logger.setLevel(logging.DEBUG)
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
            )
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)

    def enable_json(self) -> None:
        """切换为JSON结构化输出。"""
        for handler in self._logger.handlers:
            handler.setFormatter(JsonFormatter())

    def debug(self, message: str) -> None:
        self._logger.debug(message)

    def info(self, message: str) -> None:
        self._logger.info(message)

    def warning(self, message: str) -> None:
        self._logger.warning(message)

    def error(self, message: str) -> None:
        self._logger.error(message)

    def critical(self, message: str) -> None:
        self._logger.critical(message)


def get_logger() -> AgentLogger:
    """
    获取日志器实例。

    Returns:
        AgentLogger实例。
    """
    return AgentLogger()
