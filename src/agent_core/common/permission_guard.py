"""
权限最小化模块。

实现模块级权限隔离，每个模块只能访问其声明所需的资源。

第一性原理：
- 最小权限原则：模块只能访问必需资源
- 显式授权：所有权限必须显式声明
- 运行时强制：权限检查在运行时执行
"""

from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set

from agent_core.common.exceptions import ParameterInvalidException
from agent_core.common.logger import get_logger


class Permission(Enum):
    """权限枚举。"""

    FILE_READ = auto()
    FILE_WRITE = auto()
    NETWORK = auto()
    EXECUTE = auto()
    MEMORY_HIGH = auto()
    CONFIG_READ = auto()
    CONFIG_WRITE = auto()


class PermissionGuard:
    """
    权限守卫。

    管理模块权限，运行时拦截越权访问。
    """

    def __init__(self) -> None:
        self._grants: Dict[str, Set[Permission]] = {}
        self._logger = get_logger()

    def register_module(
        self, module_name: str, permissions: List[Permission]
    ) -> None:
        """
        注册模块及其权限。

        Args:
            module_name: 模块名称。
            permissions: 权限列表。
        """
        self._grants[module_name] = set(permissions)
        self._logger.info(
            f"[PermissionGuard] {module_name} granted {len(permissions)} permissions"
        )

    def check(self, module_name: str, permission: Permission) -> bool:
        """
        检查模块是否拥有指定权限。

        Args:
            module_name: 模块名称。
            permission: 权限。

        Returns:
            有权限返回True，否则返回False。
        """
        grants = self._grants.get(module_name, set())
        if permission in grants:
            return True
        self._logger.warning(
            f"[PermissionGuard] {module_name} lacks {permission.name}"
        )
        return False

    def require(self, module_name: str, permission: Permission) -> None:
        """
        要求模块必须拥有指定权限，否则抛出异常。

        Args:
            module_name: 模块名称。
            permission: 权限。

        Raises:
            ParameterInvalidException: 无权限时抛出。
        """
        if not self.check(module_name, permission):
            raise ParameterInvalidException(
                f"Module {module_name} requires {permission.name}"
            )

    def revoke(self, module_name: str, permission: Permission) -> None:
        """
        撤销模块的指定权限。

        Args:
            module_name: 模块名称。
            permission: 权限。
        """
        grants = self._grants.get(module_name, set())
        grants.discard(permission)
        self._logger.info(
            f"[PermissionGuard] Revoked {permission.name} from {module_name}"
        )

    def list_permissions(self, module_name: str) -> List[str]:
        """
        列出模块的所有权限。

        Args:
            module_name: 模块名称。

        Returns:
            权限名称列表。
        """
        grants = self._grants.get(module_name, set())
        return [p.name for p in grants]

    def unregister_module(self, module_name: str) -> None:
        """
        注销模块，回收所有权限。

        Args:
            module_name: 模块名称。
        """
        if module_name in self._grants:
            del self._grants[module_name]
            self._logger.info(
                f"[PermissionGuard] Unregistered {module_name}"
            )
