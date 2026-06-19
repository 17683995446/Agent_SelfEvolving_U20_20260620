"""
全局异常定义模块。

所有业务异常必须继承自本模块定义的基类，禁止随意抛出裸Exception。
"""

from .constants import ErrorCode


class AgentException(Exception):
    """
    Agent业务异常基类。

    Args:
        error_code: 错误码枚举值。
        message: 错误描述信息。
    """

    def __init__(self, error_code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class ParameterInvalidException(AgentException):
    """
    参数无效异常。
    """

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.PARAM_INVALID, message)


class ParameterEmptyException(AgentException):
    """
    参数为空异常。
    """

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.PARAM_EMPTY, message)


class ParameterFormatException(AgentException):
    """
    参数格式异常。
    """

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.PARAM_FORMAT_ERROR, message)


class ParameterOutOfRangeException(AgentException):
    """
    参数超出范围异常。
    """

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.PARAM_OUT_OF_RANGE, message)


class ModuleNotInitializedException(AgentException):
    """
    模块未初始化异常。
    """

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.MODULE_NOT_INITIALIZED, message)


class ResourceLimitExceededException(AgentException):
    """
    资源限制超出异常。
    """

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.RESOURCE_LIMIT_EXCEEDED, message)
