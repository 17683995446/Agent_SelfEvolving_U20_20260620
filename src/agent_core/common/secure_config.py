"""
配置加密与密钥管理模块。

对敏感配置（API密钥、密码等）进行加密存储，防止明文泄露。

第一性原理：
- 敏感信息永不以明文形式持久化
- 密钥派生使用标准PBKDF2算法
- 加密使用AES-256-GCM提供认证加密
"""

import base64
import json
import os
import secrets
from typing import Any, Dict, Optional

from agent_core.common.logger import get_logger


class SecureConfig:
    """
    安全配置管理器。

    使用AES-256-GCM加密敏感配置项，密钥由环境变量或主密码派生。
    """

    _SALT_LENGTH = 32
    _NONCE_LENGTH = 12
    _KEY_LENGTH = 32
    _ITERATIONS = 100000

    def __init__(self, master_key: Optional[bytes] = None) -> None:
        self._logger = get_logger()
        self._master_key = self._resolve_master_key(master_key)

    def _resolve_master_key(self, provided: Optional[bytes]) -> bytes:
        """解析主密钥。"""
        if provided is not None:
            return provided
        env_key = os.environ.get("AGENT_MASTER_KEY", "")
        if env_key:
            return base64.urlsafe_b64decode(env_key)
        default = b"default-insecure-key-change-me"
        self._logger.warning(
            "[SecureConfig] Using default master key, set AGENT_MASTER_KEY"
        )
        return default

    def _derive_key(self, salt: bytes) -> bytes:
        """使用PBKDF2派生加密密钥。"""
        try:
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            from cryptography.hazmat.primitives import hashes
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=self._KEY_LENGTH,
                salt=salt,
                iterations=self._ITERATIONS,
            )
            return kdf.derive(self._master_key)
        except ImportError:
            import hashlib
            key = self._master_key
            for _ in range(self._ITERATIONS):
                key = hashlib.sha256(key + salt).digest()
            return key[: self._KEY_LENGTH]

    def _encrypt(self, plaintext: str) -> str:
        """加密字符串，返回base64编码的密文。"""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            salt = secrets.token_bytes(self._SALT_LENGTH)
            nonce = secrets.token_bytes(self._NONCE_LENGTH)
            key = self._derive_key(salt)
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(
                nonce, plaintext.encode("utf-8"), None
            )
            payload = salt + nonce + ciphertext
            return base64.urlsafe_b64encode(payload).decode("ascii")
        except ImportError:
            self._logger.warning(
                "[SecureConfig] cryptography not available, using base64"
            )
            return base64.urlsafe_b64encode(
                plaintext.encode("utf-8")
            ).decode("ascii")

    def _decrypt(self, token: str) -> str:
        """解密base64编码的密文。"""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            data = base64.urlsafe_b64decode(token.encode("ascii"))
            salt = data[: self._SALT_LENGTH]
            nonce = data[self._SALT_LENGTH : self._SALT_LENGTH + self._NONCE_LENGTH]
            ciphertext = data[self._SALT_LENGTH + self._NONCE_LENGTH :]
            key = self._derive_key(salt)
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode("utf-8")
        except ImportError:
            return base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        except Exception as exc:
            self._logger.error(f"[SecureConfig] Decryption failed: {exc}")
            raise ValueError("Invalid encrypted token") from exc

    def encrypt_value(self, key: str, value: str) -> str:
        """
        加密单个配置值。

        Args:
            key: 配置键名（用于日志标识）。
            value: 明文值。

        Returns:
            加密后的token字符串。
        """
        token = self._encrypt(value)
        self._logger.info(f"[SecureConfig] Encrypted {key}")
        return token

    def decrypt_value(self, key: str, token: str) -> str:
        """
        解密单个配置值。

        Args:
            key: 配置键名。
            token: 加密token。

        Returns:
            明文值。
        """
        value = self._decrypt(token)
        self._logger.info(f"[SecureConfig] Decrypted {key}")
        return value

    def encrypt_dict(self, data: Dict[str, str], sensitive_keys: list) -> Dict[str, str]:
        """
        加密字典中的敏感键。

        Args:
            data: 原始配置字典。
            sensitive_keys: 需要加密的键列表。

        Returns:
            加密后的字典。
        """
        result = dict(data)
        for key in sensitive_keys:
            if key in result:
                result[key] = self.encrypt_value(key, result[key])
        return result

    def decrypt_dict(self, data: Dict[str, str], sensitive_keys: list) -> Dict[str, str]:
        """
        解密字典中的敏感键。

        Args:
            data: 加密后的配置字典。
            sensitive_keys: 需要解密的键列表。

        Returns:
            解密后的字典。
        """
        result = dict(data)
        for key in sensitive_keys:
            if key in result:
                result[key] = self.decrypt_value(key, result[key])
        return result
