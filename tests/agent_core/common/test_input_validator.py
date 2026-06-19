"""
输入验证与消毒模块测试。

覆盖：字符串消毒、数值校验、路径校验、字典校验、枚举校验、列表校验。
"""

import os
import tempfile

import pytest

from agent_core.common.input_validator import InputValidator
from agent_core.common.exceptions import (
    ParameterEmptyException,
    ParameterFormatException,
    ParameterInvalidException,
    ParameterOutOfRangeException,
)


class TestInputValidator:
    """InputValidator测试类。"""

    @pytest.fixture
    def validator(self):
        """创建验证器实例。"""
        return InputValidator()

    def test_sanitize_string_normal(self, validator):
        """测试正常字符串消毒。"""
        result = validator.sanitize_string("hello")
        assert result == "hello"

    def test_sanitize_string_empty_not_allowed(self, validator):
        """测试空字符串不允许。"""
        with pytest.raises(ParameterEmptyException):
            validator.sanitize_string("")

    def test_sanitize_string_empty_allowed(self, validator):
        """测试空字符串允许。"""
        result = validator.sanitize_string("", allow_empty=True)
        assert result == ""

    def test_sanitize_string_control_chars(self, validator):
        """测试控制字符被移除。"""
        result = validator.sanitize_string("he\x00l\x01lo")
        assert result == "hello"

    def test_sanitize_string_too_long(self, validator):
        """测试超长字符串抛出异常。"""
        with pytest.raises(ParameterOutOfRangeException):
            validator.sanitize_string("a" * 20000)

    def test_sanitize_string_non_string(self, validator):
        """测试非字符串输入抛出异常。"""
        with pytest.raises(ParameterInvalidException):
            validator.sanitize_string(123)

    def test_validate_numeric_normal(self, validator):
        """测试正常数值校验。"""
        result = validator.validate_numeric(5.5, 0.0, 10.0)
        assert result == 5.5

    def test_validate_numeric_int(self, validator):
        """测试整数输入。"""
        result = validator.validate_numeric(5, 0, 10)
        assert result == 5.0

    def test_validate_numeric_bool_rejected(self, validator):
        """测试布尔值被拒绝。"""
        with pytest.raises(ParameterInvalidException):
            validator.validate_numeric(True)

    def test_validate_numeric_below_min(self, validator):
        """测试低于最小值。"""
        with pytest.raises(ParameterOutOfRangeException):
            validator.validate_numeric(-1.0, 0.0, 10.0)

    def test_validate_numeric_above_max(self, validator):
        """测试高于最大值。"""
        with pytest.raises(ParameterOutOfRangeException):
            validator.validate_numeric(11.0, 0.0, 10.0)

    def test_validate_numeric_invalid(self, validator):
        """测试非数值输入。"""
        with pytest.raises(ParameterInvalidException):
            validator.validate_numeric("abc")

    def test_validate_path_normal(self, validator):
        """测试正常路径校验。"""
        result = validator.validate_path("/tmp/test.py")
        assert result == "/tmp/test.py"

    def test_validate_path_traversal(self, validator):
        """测试路径遍历检测。"""
        with tempfile.TemporaryDirectory() as base:
            with pytest.raises(ParameterFormatException):
                validator.validate_path("../escape", base_dir=base)

    def test_validate_path_must_exist(self, validator):
        """测试必须存在的路径。"""
        with pytest.raises(ParameterFormatException):
            validator.validate_path("/nonexistent/file.py", must_exist=True)

    def test_validate_path_illegal_chars(self, validator):
        """测试非法字符路径。"""
        with pytest.raises(ParameterInvalidException):
            validator.validate_path("/tmp/test;rm -rf")

    def test_validate_dict_normal(self, validator):
        """测试正常字典校验。"""
        data = {"a": 1, "b": 2}
        result = validator.validate_dict(data)
        assert result == data

    def test_validate_dict_required_keys(self, validator):
        """测试必填键校验。"""
        with pytest.raises(ParameterEmptyException):
            validator.validate_dict({"a": 1}, required_keys=["a", "b"])

    def test_validate_dict_allowed_keys(self, validator):
        """测试允许键校验。"""
        with pytest.raises(ParameterInvalidException):
            validator.validate_dict(
                {"a": 1, "c": 2}, allowed_keys=["a", "b"]
            )

    def test_validate_dict_depth(self, validator):
        """测试嵌套深度校验。"""
        data = {"a": {"b": {"c": {"d": {"e": 1}}}}}
        with pytest.raises(ParameterOutOfRangeException):
            validator.validate_dict(data, max_depth=3)

    def test_validate_dict_too_many_keys(self, validator):
        """测试键数量超限。"""
        data = {f"k{i}": i for i in range(101)}
        with pytest.raises(ParameterOutOfRangeException):
            validator.validate_dict(data)

    def test_validate_choice_valid(self, validator):
        """测试有效枚举值。"""
        result = validator.validate_choice("a", ["a", "b", "c"])
        assert result == "a"

    def test_validate_choice_invalid(self, validator):
        """测试无效枚举值。"""
        with pytest.raises(ParameterInvalidException):
            validator.validate_choice("d", ["a", "b", "c"])

    def test_validate_list_normal(self, validator):
        """测试正常列表校验。"""
        result = validator.validate_list([1, 2, 3], 1, 5)
        assert result == [1, 2, 3]

    def test_validate_list_too_short(self, validator):
        """测试列表太短。"""
        with pytest.raises(ParameterOutOfRangeException):
            validator.validate_list([], min_length=1)

    def test_validate_list_too_long(self, validator):
        """测试列表太长。"""
        with pytest.raises(ParameterOutOfRangeException):
            validator.validate_list([1] * 11, max_length=10)

    def test_validate_list_non_list(self, validator):
        """测试非列表输入。"""
        with pytest.raises(ParameterInvalidException):
            validator.validate_list("not a list")

    def test_validate_list_item_validator(self, validator):
        """测试列表项校验。"""
        result = validator.validate_list(
            [1, 2, 3], item_validator=lambda x: validator.validate_numeric(x, 0, 5)
        )
        assert result == [1, 2, 3]

    def test_validate_list_item_invalid(self, validator):
        """测试列表项校验失败。"""
        with pytest.raises(ParameterInvalidException):
            validator.validate_list(
                [1, 10], item_validator=lambda x: validator.validate_numeric(x, 0, 5)
            )
