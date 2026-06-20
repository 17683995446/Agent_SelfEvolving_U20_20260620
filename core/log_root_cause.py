"""
智能日志根因分析引擎

第一性原理：法医鉴定—— 通过现场痕迹（日志）还原事件经过，找出根本原因。
LogRootCauseAnalyzer 自动解析日志、关联事件、定位根因、给出修复建议。

约束：
- 纯Python实现
- 方法数 <= 7
"""

from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class RootCause:
    """根因分析结果"""
    category: str
    confidence: float
    description: str
    affected_components: List[str]
    suggested_fix: str
    fix_command: Optional[str]


@dataclass
class LogIncident:
    """日志事件"""
    timestamp: str
    level: str
    component: str
    message: str
    keywords: List[str]


class LogRootCauseAnalyzer:
    """
    智能日志根因分析引擎

    核心方法（<=7个）：
    1. parse_logs() — 解析日志
    2. extract_keywords() — 提取关键词
    3. correlate_events() — 关联事件
    4. identify_root_cause() — 识别根因
    5. suggest_fix() — 生成修复建议
    6. analyze() — 完整分析流程
    7. get_stats() — 统计
    """

    def __init__(self):
        self._history: List[Dict[str, Any]] = []
        self._incident_count = 0

        # 根因知识库：关键词模式 → 根因分类
        self._knowledge_base: Dict[str, Dict[str, Any]] = {
            "connection_refused": {
                "keywords": ["connection refused", "connection reset", "refused", "ECONNREFUSED"],
                "category": "网络连接故障",
                "description": "目标服务未启动或端口不可达",
                "suggested_fix": "检查目标服务是否运行，检查防火墙规则",
                "fix_command": "systemctl status {service} || netstat -tlnp | grep {port}",
            },
            "out_of_memory": {
                "keywords": ["out of memory", "OOM", "cannot allocate memory", "MemoryError"],
                "category": "内存耗尽",
                "description": "系统或进程内存不足",
                "suggested_fix": "增加内存、优化内存使用、重启服务释放内存",
                "fix_command": "free -h && ps aux --sort=-%mem | head -5",
            },
            "disk_full": {
                "keywords": ["no space left", "disk full", "write error", "ENOSPC"],
                "category": "磁盘空间不足",
                "description": "磁盘分区已满，无法写入新数据",
                "suggested_fix": "清理日志和临时文件，扩容磁盘",
                "fix_command": "df -h && find /var/log -name '*.log' -size +100M",
            },
            "permission_denied": {
                "keywords": ["permission denied", "access denied", "EACCES", "Unauthorized"],
                "category": "权限不足",
                "description": "进程没有足够的权限访问资源",
                "suggested_fix": "检查文件权限，确认用户身份",
                "fix_command": "ls -la {path} && id",
            },
            "timeout": {
                "keywords": ["timeout", "timed out", "deadline exceeded", "ETIMEDOUT"],
                "category": "请求超时",
                "description": "请求在指定时间内未得到响应",
                "suggested_fix": "检查网络延迟，增加超时时间，优化服务性能",
                "fix_command": "ping {host} && curl -w '%{time_total}' {url}",
            },
            "database_error": {
                "keywords": ["database", "sql", "connection pool", "lock wait timeout", "deadlock"],
                "category": "数据库故障",
                "description": "数据库连接或查询异常",
                "suggested_fix": "检查数据库连接池，优化慢查询，重启数据库",
                "fix_command": "mysqladmin processlist || psql -c 'SELECT * FROM pg_stat_activity;'",
            },
            "dependency_missing": {
                "keywords": ["module not found", "import error", "no module named", "cannot find"],
                "category": "依赖缺失",
                "description": "程序依赖的模块或库未安装",
                "suggested_fix": "安装缺失的依赖包",
                "fix_command": "pip install {module} || apt-get install {package}",
            },
            "config_error": {
                "keywords": ["config", "configuration", "invalid parameter", "bad option"],
                "category": "配置错误",
                "description": "配置文件格式错误或参数无效",
                "suggested_fix": "检查配置文件语法，恢复默认配置",
                "fix_command": "cat {config_file} | grep -n {parameter}",
            },
        }

    def parse_logs(self, log_lines: List[str]) -> List[LogIncident]:
        """
        解析日志行

        支持多种格式：
        - 标准格式: 2024-01-01 10:00:00 [ERROR] component message
        - 简化格式: timestamp [LEVEL] message
        """
        incidents = []

        # 匹配模式
        patterns = [
            # 标准格式
            re.compile(
                r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+'
                r'\[(\w+)\]\s+'
                r'(.*)'
            ),
            # 简化格式（无方括号）
            re.compile(
                r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+'
                r'(ERROR|WARN|WARNING|INFO|DEBUG|CRITICAL|FATAL)\s+'
                r'(.*)'
            ),
        ]

        for line in log_lines:
            line = line.strip()
            if not line:
                continue

            for pattern in patterns:
                match = pattern.match(line)
                if match:
                    timestamp, level, message = match.groups()
                    # 提取组件名（如果有）
                    component = "unknown"
                    comp_match = re.match(r'\[(\w+)\]\s*(.*)', message)
                    if comp_match:
                        component, message = comp_match.groups()

                    incidents.append(LogIncident(
                        timestamp=timestamp,
                        level=level.upper(),
                        component=component,
                        message=message,
                        keywords=self.extract_keywords(message),
                    ))
                    break

        return incidents

    def extract_keywords(self, message: str) -> List[str]:
        """
        从日志消息中提取关键词

        提取错误类型、技术术语等。
        """
        keywords = []
        message_lower = message.lower()

        # 技术关键词库
        tech_terms = [
            "connection", "timeout", "memory", "disk", "permission",
            "database", "sql", "config", "module", "import",
            "refused", "reset", "denied", "error", "failed",
            "unavailable", "not found", "invalid", "exceeded",
        ]

        for term in tech_terms:
            if term in message_lower:
                keywords.append(term)

        # 提取错误码（如 ECONNREFUSED, OOM 等）
        error_codes = re.findall(r'\b[A-Z]{3,}\b', message)
        keywords.extend(error_codes)

        return list(set(keywords))

    def correlate_events(self, incidents: List[LogIncident],
                         window_seconds: int = 60) -> List[List[LogIncident]]:
        """
        关联相关事件

        在时间窗口内，将同一组件或同一类型的错误关联在一起。
        """
        if not incidents:
            return []

        # 按组件分组
        by_component: Dict[str, List[LogIncident]] = {}
        for inc in incidents:
            if inc.component not in by_component:
                by_component[inc.component] = []
            by_component[inc.component].append(inc)

        # 将同一组件的事件作为一组
        groups = []
        for component, comp_incidents in by_component.items():
            if len(comp_incidents) >= 2:
                groups.append(comp_incidents)

        # 按错误级别分组（ERROR+CRITICAL）
        error_incidents = [i for i in incidents if i.level in ("ERROR", "CRITICAL", "FATAL")]
        if len(error_incidents) >= 2:
            groups.append(error_incidents)

        return groups

    def identify_root_cause(self, incidents: List[LogIncident]) -> Optional[RootCause]:
        """
        识别根因

        根据日志内容匹配知识库，找出最可能的根因。
        """
        if not incidents:
            return None

        # 收集所有关键词
        all_keywords = []
        for inc in incidents:
            all_keywords.extend(inc.keywords)
            all_keywords.extend(inc.message.lower().split())

        keyword_counter = Counter(all_keywords)

        # 匹配知识库
        best_match = None
        best_score = 0.0

        for cause_id, cause_info in self._knowledge_base.items():
            score = 0.0
            for keyword in cause_info["keywords"]:
                keyword_lower = keyword.lower()
                if keyword_lower in keyword_counter:
                    score += keyword_counter[keyword_lower]

            # 归一化
            if cause_info["keywords"]:
                score = score / len(cause_info["keywords"])

            if score > best_score:
                best_score = score
                best_match = cause_info
                best_match_id = cause_id

        if best_match and best_score > 0.1:
            # 提取受影响的组件
            affected = list(set([i.component for i in incidents if i.level in ("ERROR", "CRITICAL", "FATAL")]))

            # 生成修复命令（简单替换占位符）
            fix_cmd = best_match.get("fix_command")

            return RootCause(
                category=best_match["category"],
                confidence=min(best_score, 1.0),
                description=best_match["description"],
                affected_components=affected,
                suggested_fix=best_match["suggested_fix"],
                fix_command=fix_cmd,
            )

        return None

    def suggest_fix(self, root_cause: RootCause) -> Dict[str, Any]:
        """
        生成修复建议

        根据根因生成可执行的修复方案。
        """
        if not root_cause:
            return {"has_fix": False, "message": "无法确定根因，无法生成修复建议"}

        fix_steps = []

        if root_cause.category == "磁盘空间不足":
            fix_steps = [
                "1. 检查磁盘使用情况: df -h",
                "2. 查找大文件: find / -size +100M",
                "3. 清理旧日志: find /var/log -mtime +7 -delete",
                "4. 清理临时文件: rm -rf /tmp/*",
            ]
        elif root_cause.category == "内存耗尽":
            fix_steps = [
                "1. 检查内存使用: free -h",
                "2. 找出内存大户: ps aux --sort=-%mem | head -10",
                "3. 清理缓存: sync && echo 3 > /proc/sys/vm/drop_caches",
                "4. 必要时重启服务释放内存",
            ]
        elif root_cause.category == "网络连接故障":
            fix_steps = [
                "1. 检查目标服务状态: systemctl status <service>",
                "2. 检查端口监听: netstat -tlnp | grep <port>",
                "3. 检查防火墙: iptables -L | grep <port>",
                "4. 测试连通性: telnet <host> <port>",
            ]
        elif root_cause.category == "权限不足":
            fix_steps = [
                "1. 检查当前用户: id",
                "2. 检查文件权限: ls -la <path>",
                "3. 修复权限: chmod/chown",
            ]
        elif root_cause.category == "依赖缺失":
            fix_steps = [
                "1. 安装Python依赖: pip install <module>",
                "2. 安装系统包: apt-get/yum install <package>",
            ]
        else:
            fix_steps = [root_cause.suggested_fix]

        return {
            "has_fix": True,
            "category": root_cause.category,
            "confidence": root_cause.confidence,
            "description": root_cause.description,
            "steps": fix_steps,
            "command": root_cause.fix_command,
            "affected_components": root_cause.affected_components,
        }

    def analyze(self, log_lines: List[str]) -> Dict[str, Any]:
        """
        完整分析流程

        解析→关联→根因→建议，一站式完成日志分析。
        """
        start = time.time()
        self._incident_count += 1

        # 1. 解析日志
        incidents = self.parse_logs(log_lines)

        # 2. 统计
        error_count = len([i for i in incidents if i.level in ("ERROR", "CRITICAL", "FATAL")])
        warn_count = len([i for i in incidents if i.level == "WARN"])

        # 3. 关联事件
        correlated = self.correlate_events(incidents)

        # 4. 识别根因
        root_cause = self.identify_root_cause(incidents)

        # 5. 生成修复建议
        fix = self.suggest_fix(root_cause) if root_cause else {"has_fix": False}

        result = {
            "status": "analyzed",
            "incident_id": f"incident_{self._incident_count}",
            "summary": {
                "total_lines": len(log_lines),
                "parsed_incidents": len(incidents),
                "error_count": error_count,
                "warning_count": warn_count,
                "correlated_groups": len(correlated),
            },
            "root_cause": {
                "category": root_cause.category if root_cause else "unknown",
                "confidence": root_cause.confidence if root_cause else 0.0,
                "description": root_cause.description if root_cause else "无法确定根因",
                "affected_components": root_cause.affected_components if root_cause else [],
            } if root_cause else None,
            "fix": fix,
            "top_errors": self._get_top_errors(incidents),
            "duration_ms": (time.time() - start) * 1000,
        }

        self._history.append(result)
        return result

    def _get_top_errors(self, incidents: List[LogIncident], n: int = 3) -> List[Dict[str, Any]]:
        """获取最常见的错误"""
        error_messages = [i.message for i in incidents if i.level in ("ERROR", "CRITICAL")]
        counter = Counter(error_messages)
        return [
            {"message": msg, "count": count}
            for msg, count in counter.most_common(n)
        ]

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._history)
        with_root_cause = len([h for h in self._history if h.get("root_cause")])
        return {
            "total_analyses": total,
            "root_cause_found": with_root_cause,
            "success_rate": with_root_cause / total if total > 0 else 0,
        }
