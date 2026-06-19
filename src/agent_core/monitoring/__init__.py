"""
监控模块包初始化文件。

提供Web Dashboard实时展示Agent运行状态。
"""

from .dashboard_server import DashboardServer, get_dashboard_server

__all__ = ["DashboardServer", "get_dashboard_server"]
