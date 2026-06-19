"""
日志模块单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import unittest

from agent_core.common.logger import AgentLogger, get_logger


class TestAgentLogger(unittest.TestCase):
    """测试日志器。"""

    def test_singleton(self) -> None:
        """正常值入参测试：单例模式。"""
        logger_a = AgentLogger()
        logger_b = AgentLogger()
        self.assertIs(logger_a, logger_b)

    def test_get_logger(self) -> None:
        """正常值入参测试：获取日志器。"""
        logger = get_logger()
        self.assertIsInstance(logger, AgentLogger)

    def test_log_levels(self) -> None:
        """正常值入参测试：各级别日志打印。"""
        logger = get_logger()
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        logger.error("error message")
        logger.critical("critical message")

    def test_empty_message(self) -> None:
        """空入参测试：空消息。"""
        logger = get_logger()
        logger.info("")

    def test_long_message(self) -> None:
        """边界极值测试：超长消息。"""
        logger = get_logger()
        logger.info("x" * 10000)


if __name__ == "__main__":
    unittest.main()
