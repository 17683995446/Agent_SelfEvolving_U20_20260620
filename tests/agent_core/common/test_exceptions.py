"""
异常模块单元测试。

覆盖异常定义的四类用例。
"""

import unittest

from agent_core.common.exceptions import (
    AgentException,
    ParameterInvalidException,
    ParameterEmptyException,
    ParameterFormatException,
    ParameterOutOfRangeException,
    ModuleNotInitializedException,
    ResourceLimitExceededException,
)
from agent_core.common.constants import ErrorCode


class TestExceptions(unittest.TestCase):
    """测试异常定义。"""

    def test_agent_exception_attributes(self) -> None:
        """正常值测试：基类属性正确。"""
        exc = AgentException(ErrorCode.SUCCESS, "test")
        self.assertEqual(exc.error_code, ErrorCode.SUCCESS)
        self.assertEqual(exc.message, "test")
        self.assertEqual(str(exc), "test")

    def test_parameter_invalid_exception(self) -> None:
        """正常值测试：参数无效异常。"""
        exc = ParameterInvalidException("bad param")
        self.assertEqual(exc.error_code, ErrorCode.PARAM_INVALID)
        self.assertEqual(exc.message, "bad param")

    def test_parameter_empty_exception(self) -> None:
        """正常值测试：参数为空异常。"""
        exc = ParameterEmptyException("empty param")
        self.assertEqual(exc.error_code, ErrorCode.PARAM_EMPTY)

    def test_parameter_format_exception(self) -> None:
        """正常值测试：参数格式异常。"""
        exc = ParameterFormatException("format error")
        self.assertEqual(exc.error_code, ErrorCode.PARAM_FORMAT_ERROR)

    def test_parameter_out_of_range_exception(self) -> None:
        """正常值测试：参数越界异常。"""
        exc = ParameterOutOfRangeException("out of range")
        self.assertEqual(exc.error_code, ErrorCode.PARAM_OUT_OF_RANGE)

    def test_module_not_initialized_exception(self) -> None:
        """正常值测试：模块未初始化异常。"""
        exc = ModuleNotInitializedException("not ready")
        self.assertEqual(exc.error_code, ErrorCode.MODULE_NOT_INITIALIZED)

    def test_resource_limit_exceeded_exception(self) -> None:
        """正常值测试：资源超限异常。"""
        exc = ResourceLimitExceededException("too much")
        self.assertEqual(exc.error_code, ErrorCode.RESOURCE_LIMIT_EXCEEDED)

    def test_exception_is_catchable(self) -> None:
        """正常值测试：异常可被捕获。"""
        try:
            raise ParameterInvalidException("catch me")
        except AgentException as exc:
            self.assertEqual(exc.error_code, ErrorCode.PARAM_INVALID)

    def test_exception_empty_message(self) -> None:
        """边界测试：空消息。"""
        exc = ParameterInvalidException("")
        self.assertEqual(exc.message, "")

    def test_all_exceptions_inherit_agent_exception(self) -> None:
        """正常值测试：所有异常继承基类。"""
        exceptions = [
            ParameterInvalidException("x"),
            ParameterEmptyException("x"),
            ParameterFormatException("x"),
            ParameterOutOfRangeException("x"),
            ModuleNotInitializedException("x"),
            ResourceLimitExceededException("x"),
        ]
        for exc in exceptions:
            self.assertIsInstance(exc, AgentException)


if __name__ == "__main__":
    unittest.main()
