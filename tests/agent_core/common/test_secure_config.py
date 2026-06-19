"""
配置加密与密钥管理模块测试。

覆盖：加密解密、字典加解密、错误处理、主密钥解析。
"""

import os

import pytest

from agent_core.common.secure_config import SecureConfig


class TestSecureConfig:
    """SecureConfig测试类。"""

    @pytest.fixture
    def secure(self):
        """创建安全配置实例。"""
        return SecureConfig(master_key=b"test-key-32-bytes-long!!!!!")

    def test_encrypt_decrypt_roundtrip(self, secure):
        """测试加密解密往返。"""
        original = "my-secret-api-key"
        token = secure.encrypt_value("api_key", original)
        assert token != original
        decrypted = secure.decrypt_value("api_key", token)
        assert decrypted == original

    def test_encrypt_dict(self, secure):
        """测试字典加密。"""
        data = {"api_key": "secret", "name": "public"}
        encrypted = secure.encrypt_dict(data, ["api_key"])
        assert encrypted["api_key"] != "secret"
        assert encrypted["name"] == "public"

    def test_decrypt_dict(self, secure):
        """测试字典解密。"""
        data = {"api_key": "secret", "name": "public"}
        encrypted = secure.encrypt_dict(data, ["api_key"])
        decrypted = secure.decrypt_dict(encrypted, ["api_key"])
        assert decrypted["api_key"] == "secret"
        assert decrypted["name"] == "public"

    def test_decrypt_invalid_token(self, secure):
        """测试无效token解密失败。"""
        with pytest.raises(ValueError):
            secure.decrypt_value("key", "not-valid-token!!!")

    def test_master_key_from_env(self, monkeypatch):
        """测试从环境变量读取主密钥。"""
        import base64
        key = base64.urlsafe_b64encode(b"env-key-32-bytes-long!!!!!").decode()
        monkeypatch.setenv("AGENT_MASTER_KEY", key)
        secure = SecureConfig()
        assert secure._master_key == b"env-key-32-bytes-long!!!!!"

    def test_master_key_provided(self):
        """测试显式传入主密钥。"""
        secure = SecureConfig(master_key=b"provided-key-32-bytes-long")
        assert secure._master_key == b"provided-key-32-bytes-long"

    def test_different_keys_produce_different_tokens(self, secure):
        """测试相同明文不同密文。"""
        token1 = secure.encrypt_value("k", "secret")
        token2 = secure.encrypt_value("k", "secret")
        assert token1 != token2
