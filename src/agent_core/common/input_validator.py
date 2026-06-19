"""
输入验证与消毒模块。

对所有外部输入进行严格校验，防止非法数据流入系统。

第一性原理：
- 不信任任何外部输入
- 校验失败立即拒绝，不尝试自动修正
- 消毒只去除危险字符，不改变语义
"""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from agent_core.common.exceptions import (
    ParameterEmptyException,
    ParameterFormatException,
    ParameterInvalidException,
    ParameterOutOfRangeException,
)
from agent_core.common.logger import get_logger


class InputValidator:
    """
    输入验证器。

    提供字符串、数值、路径、字典等常用输入的校验与消毒方法。
    """

    _MAX_STRING_LENGTH = 10000
    _MAX_DICT_DEPTH = 5
    _MAX_DICT_KEYS = 100
    _ALLOWED_PATH_PATTERN = re.compile(r"^[\w\-./\\]+$")
    _CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]")

    def __init__(self) -> None:
        self._logger = get_logger()

    def sanitize_string(
        self,
        value: str,
        max_length: int = _MAX_STRING_LENGTH,
        allow_empty: bool = False,
    ) -> str:
        """
        消毒字符串。

        Args:
            value: 输入字符串。
            max_length: 最大长度。
            allow_empty: 是否允许空字符串。

        Returns:
            消毒后的字符串。

        Raises:
            ParameterEmptyException: 空字符串不允许时抛出。
            ParameterOutOfRangeException: 超出最大长度时抛出。
        """
        if not isinstance(value, str):
            raise ParameterInvalidException(
                f"Expected str, got {type(value).__name__}"
            )
        if not allow_empty and len(value) == 0:
            raise ParameterEmptyException("String must not be empty")
        if len(value) > max_length:
            raise ParameterOutOfRangeException(
                f"String length {len(value)} exceeds max {max_length}"
            )
        cleaned = self._CONTROL_CHAR_PATTERN.sub("", value)
        if cleaned != value:
            self._logger.warning("[InputValidator] Control chars removed")
        return cleaned

    def validate_numeric(
        self,
        value: Any,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
    ) -> float:
        """
        校验数值。

        Args:
            value: 输入值。
            min_value: 最小值。
            max_value: 最大值。

        Returns:
            浮点数值。

        Raises:
            ParameterInvalidException: 非数值时抛出。
            ParameterOutOfRangeException: 超出范围时抛出。
        """
        if isinstance(value, bool):
            raise ParameterInvalidException("Boolean is not a valid numeric")
        try:
            num = float(value)
        except (TypeError, ValueError) as exc:
            raise ParameterInvalidException(
                f"Cannot convert to float: {exc}"
            ) from exc
        if min_value is not None and num < min_value:
            raise ParameterOutOfRangeException(
                f"Value {num} below minimum {min_value}"
            )
        if max_value is not None and num > max_value:
            raise ParameterOutOfRangeException(
                f"Value {num} above maximum {max_value}"
            )
        return num

    def validate_path(
        self, path: str, must_exist: bool = False, base_dir: Optional[str] = None
    ) -> str:
        """
        校验文件路径。

        Args:
            path: 输入路径。
            must_exist: 是否要求文件已存在。
            base_dir: 限制的基础目录。

        Returns:
            标准化后的绝对路径。

        Raises:
            ParameterInvalidException: 路径包含非法字符时抛出。
            ParameterFormatException: 路径遍历攻击时抛出。
        """
        if not isinstance(path, str):
            raise ParameterInvalidException("Path must be a string")
        cleaned = self.sanitize_string(path, max_length=4096)
        if not self._ALLOWED_PATH_PATTERN.match(cleaned):
            raise ParameterInvalidException(
                "Path contains illegal characters"
            )
        abs_path = os.path.abspath(cleaned)
        if base_dir is not None:
            abs_base = os.path.abspath(base_dir)
            if not abs_path.startswith(abs_base):
                raise ParameterFormatException(
                    "Path traversal detected"
                )
        if must_exist and not os.path.exists(abs_path):
            raise ParameterFormatException(
                f"Path does not exist: {abs_path}"
            )
        return abs_path

    def validate_dict(
        self,
        data: Any,
        required_keys: Optional[List[str]] = None,
        allowed_keys: Optional[List[str]] = None,
        max_depth: int = _MAX_DICT_DEPTH,
    ) -> Dict[str, Any]:
        """
        校验字典。

        Args:
            data: 输入数据。
            required_keys: 必填键列表。
            allowed_keys: 允许键列表。
            max_depth: 最大嵌套深度。

        Returns:
            校验后的字典。

        Raises:
            ParameterInvalidException: 非字典或结构非法时抛出。
            ParameterEmptyException: 必填键缺失时抛出。
        """
        if not isinstance(data, dict):
            raise ParameterInvalidException(
                f"Expected dict, got {type(data).__name__}"
            )
        if len(data) > self._MAX_DICT_KEYS:
            raise ParameterOutOfRangeException(
                f"Dict key count {len(data)} exceeds max {self._MAX_DICT_KEYS}"
            )
        depth = self._compute_depth(data)
        if depth > max_depth:
            raise ParameterOutOfRangeException(
                f"Dict depth {depth} exceeds max {max_depth}"
            )
        if required_keys is not None:
            missing = set(required_keys) - set(data.keys())
            if missing:
                raise ParameterEmptyException(
                    f"Missing required keys: {missing}"
                )
        if allowed_keys is not None:
            extra = set(data.keys()) - set(allowed_keys)
            if extra:
                raise ParameterInvalidException(
                    f"Disallowed keys: {extra}"
                )
        return data

    def _compute_depth(self, obj: Any, current: int = 1) -> int:
        """计算对象嵌套深度。"""
        if not isinstance(obj, dict):
            return current
        if not obj:
            return current
        return max(
            self._compute_depth(v, current + 1) for v in obj.values()
        )

    def validate_choice(
        self, value: Any, choices: List[Any]
    ) -> Any:
        """
        校验枚举值。

        Args:
            value: 输入值。
            choices: 允许值列表。

        Returns:
            原值。

        Raises:
            ParameterInvalidException: 不在允许列表时抛出。
        """
        if value not in choices:
            raise ParameterInvalidException(
                f"Value {value!r} not in allowed choices"
            )
        return value

    def validate_list(
        self,
        value: Any,
        min_length: int = 0,
        max_length: int = 10000,
        item_validator: Optional[Any] = None,
    ) -> List[Any]:
        """
        校验列表。

        Args:
            value: 输入值。
            min_length: 最小长度。
            max_length: 最大长度。
            item_validator: 单项校验函数。

        Returns:
            校验后的列表。

        Raises:
            ParameterInvalidException: 非列表或长度非法时抛出。
        """
        if not isinstance(value, list):
            raise ParameterInvalidException(
                f"Expected list, got {type(value).__name__}"
            )
        if len(value) < min_length:
            raise ParameterOutOfRangeException(
                f"List length {len(value)} below minimum {min_length}"
            )
        if len(value) > max_length:
            raise ParameterOutOfRangeException(
                f"List length {len(value)} exceeds maximum {max_length}"
            )
        if item_validator is not None:
            for i, item in enumerate(value):
                try:
                    item_validator(item)
                except Exception as exc:
                    raise ParameterInvalidException(
                        f"List item {i} invalid: {exc}"
                    ) from exc
        return value
