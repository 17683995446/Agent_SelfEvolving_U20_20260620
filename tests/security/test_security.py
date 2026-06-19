"""
安全专项测试。

覆盖：输入注入、权限越界、加密鲁棒性、审计防篡改。
"""

import pytest

from agent_core.common.input_validator import InputValidator
from agent_core.common.permission_guard import Permission, PermissionGuard
from agent_core.common.secure_config import SecureConfig
from agent_core.common.audit_logger import AuditLogger
from agent_core.common.exceptions import (
    ParameterEmptyException,
    ParameterFormatException,
    ParameterInvalidException,
    ParameterOutOfRangeException,
)


class TestInputSecurity:
    """输入安全测试。"""

    @pytest.fixture
    def validator(self):
        return InputValidator()

    def test_path_traversal_relative(self, validator):
        """测试相对路径遍历。"""
        with pytest.raises(ParameterFormatException):
            validator.validate_path("../../../etc/passwd", base_dir="/tmp")

    def test_path_traversal_absolute(self, validator):
        """测试绝对路径遍历。"""
        with pytest.raises(ParameterFormatException):
            validator.validate_path("/etc/passwd", base_dir="/tmp")

    def test_null_byte_injection(self, validator):
        """测试空字节注入。"""
        result = validator.sanitize_string("hello\x00world")
        assert "\x00" not in result

    def test_control_char_injection(self, validator):
        """测试控制字符注入。"""
        result = validator.sanitize_string("test\x1b[31mred")
        assert "\x1b" not in result

    def test_very_long_string_rejected(self, validator):
        """测试超长字符串被拒绝。"""
        with pytest.raises(ParameterOutOfRangeException):
            validator.sanitize_string("a" * 20000)

    def test_sql_injection_pattern(self, validator):
        """测试SQL注入模式在路径中被拒。"""
        with pytest.raises(ParameterInvalidException):
            validator.validate_path("/tmp/test'; DROP TABLE users; --")

    def test_command_injection_pattern(self, validator):
        """测试命令注入模式在路径中被拒。"""
        with pytest.raises(ParameterInvalidException):
            validator.validate_path("/tmp/test; rm -rf /")


class TestPermissionSecurity:
    """权限安全测试。"""

    @pytest.fixture
    def guard(self):
        return PermissionGuard()

    def test_unregistered_module_no_permissions(self, guard):
        """测试未注册模块无任何权限。"""
        assert guard.check("unknown", Permission.FILE_WRITE) is False

    def test_module_cannot_access_others_permissions(self, guard):
        """测试模块不能访问其他模块权限。"""
        guard.register_module("mod_a", [Permission.FILE_READ])
        guard.register_module("mod_b", [Permission.FILE_WRITE])
        assert guard.check("mod_a", Permission.FILE_WRITE) is False

    def test_revoke_effect_immediate(self, guard):
        """测试撤销权限立即生效。"""
        guard.register_module("mod", [Permission.NETWORK])
        guard.revoke("mod", Permission.NETWORK)
        assert guard.check("mod", Permission.NETWORK) is False

    def test_require_raises_on_violation(self, guard):
        """测试require在越权时抛出异常。"""
        guard.register_module("mod", [Permission.FILE_READ])
        with pytest.raises(ParameterInvalidException):
            guard.require("mod", Permission.EXECUTE)


class TestEncryptionSecurity:
    """加密安全测试。"""

    def test_wrong_key_decryption_fails(self):
        """测试错误密钥解密失败。"""
        secure1 = SecureConfig(master_key=b"key-one-32-bytes-long!!!!!")
        secure2 = SecureConfig(master_key=b"key-two-32-bytes-long!!!!!")
        token = secure1.encrypt_value("k", "secret")
        with pytest.raises(ValueError):
            secure2.decrypt_value("k", token)

    def test_tampered_token_fails(self):
        """测试篡改token解密失败。"""
        secure = SecureConfig(master_key=b"key-32-bytes-long!!!!!")
        token = secure.encrypt_value("k", "secret")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(ValueError):
            secure.decrypt_value("k", tampered)

    def test_same_plaintext_different_ciphertext(self):
        """测试相同明文不同密文。"""
        secure = SecureConfig(master_key=b"key-32-bytes-long!!!!!")
        t1 = secure.encrypt_value("k", "secret")
        t2 = secure.encrypt_value("k", "secret")
        assert t1 != t2


class TestAuditSecurity:
    """审计安全测试。"""

    def test_tampered_event_detected(self):
        """测试篡改事件被检测。"""
        logger = AuditLogger()
        logger.log("a", "act", "res", "ok")
        logger._events[0].actor = "attacker"
        assert logger.verify_integrity() is False

    def test_deleted_event_detected(self):
        """测试删除事件被检测。"""
        logger = AuditLogger()
        logger.log("a", "act", "res", "ok")
        logger.log("b", "act", "res", "ok")
        logger._events.pop(0)
        assert logger.verify_integrity() is False

    def test_inserted_event_detected(self):
        """测试插入事件被检测。"""
        logger = AuditLogger()
        logger.log("a", "act", "res", "ok")
        from agent_core.common.audit_logger import AuditEvent
        logger._events.insert(0, AuditEvent(0.0, "x", "x", "x", "x", {}, "fake"))
        assert logger.verify_integrity() is False
