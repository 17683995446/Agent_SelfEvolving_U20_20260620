"""
安全模块

第一性原理：生物体的生存是第一要务。安全模块确保Agent不会自我伤害或超出边界。
"""

from .resource_limiter import ResourceLimiter
from .security_guard import SecurityGuard, SecurityCheckResult, AuditRecord

__all__ = ["ResourceLimiter", "SecurityGuard", "SecurityCheckResult", "AuditRecord"]
