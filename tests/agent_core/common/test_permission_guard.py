"""
权限最小化模块测试。

覆盖：注册、检查、要求、撤销、列出、注销。
"""

import pytest

from agent_core.common.permission_guard import Permission, PermissionGuard
from agent_core.common.exceptions import ParameterInvalidException


class TestPermissionGuard:
    """PermissionGuard测试类。"""

    @pytest.fixture
    def guard(self):
        """创建权限守卫实例。"""
        return PermissionGuard()

    def test_register_and_check(self, guard):
        """测试注册后权限检查通过。"""
        guard.register_module("test_mod", [Permission.FILE_READ])
        assert guard.check("test_mod", Permission.FILE_READ) is True

    def test_check_missing_permission(self, guard):
        """测试未授权权限检查失败。"""
        guard.register_module("test_mod", [Permission.FILE_READ])
        assert guard.check("test_mod", Permission.NETWORK) is False

    def test_check_unregistered_module(self, guard):
        """测试未注册模块检查失败。"""
        assert guard.check("unknown", Permission.FILE_READ) is False

    def test_require_success(self, guard):
        """测试有权限时require不抛异常。"""
        guard.register_module("test_mod", [Permission.FILE_READ])
        guard.require("test_mod", Permission.FILE_READ)

    def test_require_failure(self, guard):
        """测试无权限时require抛异常。"""
        guard.register_module("test_mod", [Permission.FILE_READ])
        with pytest.raises(ParameterInvalidException):
            guard.require("test_mod", Permission.NETWORK)

    def test_revoke(self, guard):
        """测试撤销权限。"""
        guard.register_module("test_mod", [Permission.FILE_READ, Permission.NETWORK])
        guard.revoke("test_mod", Permission.FILE_READ)
        assert guard.check("test_mod", Permission.FILE_READ) is False
        assert guard.check("test_mod", Permission.NETWORK) is True

    def test_list_permissions(self, guard):
        """测试列出权限。"""
        guard.register_module("test_mod", [Permission.FILE_READ, Permission.NETWORK])
        perms = guard.list_permissions("test_mod")
        assert "FILE_READ" in perms
        assert "NETWORK" in perms
        assert "EXECUTE" not in perms

    def test_list_unregistered(self, guard):
        """测试列出未注册模块权限为空。"""
        assert guard.list_permissions("unknown") == []

    def test_unregister_module(self, guard):
        """测试注销模块。"""
        guard.register_module("test_mod", [Permission.FILE_READ])
        guard.unregister_module("test_mod")
        assert guard.check("test_mod", Permission.FILE_READ) is False
