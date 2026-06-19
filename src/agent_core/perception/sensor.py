"""
传感器实现模块。

提供各类系统传感器，每个传感器独立负责采集一类环境数据。
"""

import asyncio
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import psutil


class ISensor(ABC):
    """
    传感器接口基类。

    单一职责：采集一类环境数据。
    """

    @property
    @abstractmethod
    def sensor_type(self) -> str:
        """
        获取传感器类型标识。

        Returns:
            传感器类型字符串。
        """
        raise NotImplementedError

    @abstractmethod
    async def read(self) -> Dict[str, Any]:
        """
        读取传感器数据。

        Returns:
            传感器数据字典。
        """
        raise NotImplementedError


class CPUSensor(ISensor):
    """
    CPU传感器，采集处理器状态。
    """

    def __init__(self, interval_seconds: float) -> None:
        self._interval_seconds = interval_seconds

    @property
    def sensor_type(self) -> str:
        return "cpu"

    async def read(self) -> Dict[str, Any]:
        # Bug20修复：psutil.cpu_percent(interval>0)是阻塞调用，
        # 必须用asyncio.to_thread包装，避免阻塞事件循环
        # Bug31修复：3次独立psutil调用串行执行浪费时间，改为并行
        cpu_percent_task = asyncio.to_thread(
            psutil.cpu_percent, interval=self._interval_seconds
        )
        cpu_frequency_task = asyncio.to_thread(psutil.cpu_freq)
        per_cpu_task = asyncio.to_thread(psutil.cpu_percent, percpu=True)
        cpu_percent, cpu_frequency, per_cpu = await asyncio.gather(
            cpu_percent_task, cpu_frequency_task, per_cpu_task
        )
        load_average = (
            os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
        )
        return {
            "percent": cpu_percent,
            "frequency": cpu_frequency.current if cpu_frequency else 0,
            "count": psutil.cpu_count(),
            "load_avg_1m": load_average[0],
            "load_avg_5m": load_average[1],
            "load_avg_15m": load_average[2],
            "per_cpu": per_cpu,
        }


class MemorySensor(ISensor):
    """
    内存传感器，采集内存使用状态。
    """

    @property
    def sensor_type(self) -> str:
        return "memory"

    async def read(self) -> Dict[str, Any]:
        # Bug30修复：psutil调用是同步阻塞，用asyncio.to_thread包装
        virtual_memory, swap_memory = await asyncio.to_thread(
            self._read_memory_sync
        )
        return {
            "total": virtual_memory.total,
            "available": virtual_memory.available,
            "percent": virtual_memory.percent,
            "used": virtual_memory.used,
            "free": virtual_memory.free,
            "swap_total": swap_memory.total,
            "swap_used": swap_memory.used,
            "swap_percent": swap_memory.percent,
        }

    @staticmethod
    def _read_memory_sync():
        return psutil.virtual_memory(), psutil.swap_memory()


class DiskSensor(ISensor):
    """
    磁盘传感器，采集磁盘使用状态。
    """

    def __init__(self, paths: Optional[List[str]]) -> None:
        self._paths = paths if paths is not None else ["/"]

    @property
    def sensor_type(self) -> str:
        return "disk"

    async def read(self) -> Dict[str, Any]:
        # Bug30修复：psutil.disk_usage是同步阻塞，用asyncio.to_thread包装
        partitions = await asyncio.to_thread(self._read_disk_sync)
        return {"partitions": partitions}

    def _read_disk_sync(self) -> List[Dict[str, Any]]:
        partitions = []
        for path in self._paths:
            if not os.path.exists(path):
                continue
            usage = psutil.disk_usage(path)
            partitions.append({
                "path": path,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent,
            })
        return partitions


class NetworkSensor(ISensor):
    """
    网络传感器，采集网络IO状态。
    """

    @property
    def sensor_type(self) -> str:
        return "network"

    async def read(self) -> Dict[str, Any]:
        # Bug30修复：psutil.net_io_counters是同步阻塞，用asyncio.to_thread包装
        counters = await asyncio.to_thread(psutil.net_io_counters)
        return {
            "bytes_sent": counters.bytes_sent,
            "bytes_recv": counters.bytes_recv,
            "packets_sent": counters.packets_sent,
            "packets_recv": counters.packets_recv,
            "errin": counters.errin,
            "errout": counters.errout,
        }


class LogSensor(ISensor):
    """
    日志传感器，采集系统日志异常。
    """

    def __init__(self, log_paths: Optional[List[str]], max_lines: int) -> None:
        self._log_paths = log_paths if log_paths is not None else []
        self._max_lines = max_lines
        self._error_pattern = re.compile(
            r"ERROR|FATAL|CRITICAL|exception|traceback",
            re.IGNORECASE,
        )
        self._file_positions: Dict[str, int] = {}

    @property
    def sensor_type(self) -> str:
        return "log"

    async def read(self) -> Dict[str, Any]:
        # Bug33修复：文件IO是同步阻塞，用asyncio.to_thread包装
        error_count, warning_count = await asyncio.to_thread(self._read_logs_sync)
        return {
            "error_count": error_count,
            "warning_count": warning_count,
            "total_issues": error_count + warning_count,
        }

    def _read_logs_sync(self) -> tuple:
        error_count = 0
        warning_count = 0
        for path in self._log_paths:
            if not os.path.exists(path):
                continue
            try:
                lines = self._read_new_lines(path)
                error_count += sum(1 for line in lines if self._error_pattern.search(line))
                warning_count += sum(1 for line in lines if "WARNING" in line.upper())
            except Exception:
                continue
        return error_count, warning_count

    def _read_new_lines(self, path: str) -> List[str]:
        last_position = self._file_positions.get(path, 0)
        with open(path, "r", encoding="utf-8", errors="ignore") as file:
            file.seek(last_position)
            lines = file.readlines()
            self._file_positions[path] = file.tell()
        stripped = [line.strip() for line in lines]
        return stripped[-self._max_lines:]


class ProcessSensor(ISensor):
    """
    进程传感器，采集进程状态。
    """

    @property
    def sensor_type(self) -> str:
        return "process"

    async def read(self) -> Dict[str, Any]:
        # Bug20修复：process_iter可能较慢，用asyncio.to_thread包装
        process_list = await asyncio.to_thread(
            lambda: list(psutil.process_iter(["num_threads", "status"]))
        )
        total_threads = sum(p.info["num_threads"] for p in process_list)
        zombie_count = sum(
            1 for p in process_list if p.info["status"] == psutil.STATUS_ZOMBIE
        )
        return {
            "total_processes": len(process_list),
            "thread_count": total_threads,
            "zombie_count": zombie_count,
        }
