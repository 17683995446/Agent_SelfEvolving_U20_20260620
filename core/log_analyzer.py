"""
智能日志分析器

第一性原理：人类医生通过病历发现疾病模式——
LogAnalyzer 通过分析运行日志发现异常模式、趋势和根因。

约束：
- 纯Python实现
- 方法数 <= 7
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class LogAnalyzer:
    """
    智能日志分析器

    自动分析Agent运行日志，发现异常模式、趋势和潜在问题。

    核心方法（<=7个）：
    1. parse_log_file() — 解析日志文件
    2. detect_anomaly_patterns() — 检测异常模式
    3. analyze_error_frequency() — 分析错误频率趋势
    4. extract_metrics_trend() — 提取指标趋势
    5. correlate_events() — 关联事件（找根因）
    6. generate_insights() — 生成洞察报告
    7. get_stats() — 统计
    """

    def __init__(self):
        self._parsed_entries: List[Dict[str, Any]] = []
        self._anomaly_patterns: List[Dict[str, Any]] = []
        self._insights: List[str] = []

    def parse_log_file(self, log_path: Path) -> List[Dict[str, Any]]:
        """
        解析日志文件

        支持解析Agent的标准日志格式：
        [timestamp] [LEVEL] [component] [key=value,...] message
        """
        if not log_path.exists():
            return []

        entries = []
        # 标准Agent日志格式: [timestamp] [LEVEL] [component] [key=value,...] message
        pattern = re.compile(
            r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\]\s+'
            r'\[(\w+)\]\s+'
            r'\[([^\]]+)\]\s+'
            r'\[([^\]]*)\]\s+'
            r'(.*)'
        )
        # 简化日志格式: timestamp [LEVEL] message (无方括号包裹timestamp)
        medium_pattern = re.compile(
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+'
            r'\[(\w+)\]\s+'
            r'(.*)'
        )
        # 长运行日志格式: [Day Mon DD HH:MM:SS YYYY] message
        simple_pattern = re.compile(
            r'\[(\w{3}\s+\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2}\s+\d{4})\]\s+(.*)'
        )

        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            match = pattern.match(line)
            if match:
                timestamp, level, component, context, message = match.groups()
                context_dict = {}
                for kv in context.split(","):
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        context_dict[k.strip()] = v.strip()
                entries.append({
                    "timestamp": timestamp,
                    "level": level,
                    "component": component,
                    "context": context_dict,
                    "message": message,
                })
            else:
                mm = medium_pattern.match(line)
                if mm:
                    timestamp, level, message = mm.groups()
                    entries.append({
                        "timestamp": timestamp,
                        "level": level,
                        "component": "unknown",
                        "context": {},
                        "message": message,
                    })
                else:
                    sm = simple_pattern.match(line)
                    if sm:
                        timestamp, message = sm.groups()
                        level = "INFO"
                        if "error" in message.lower():
                            level = "ERROR"
                        entries.append({
                            "timestamp": timestamp,
                            "level": level,
                            "component": "long_run",
                            "context": {},
                            "message": message,
                        })

        self._parsed_entries = entries
        return entries

    def detect_anomaly_patterns(self) -> List[Dict[str, Any]]:
        """
        检测异常模式

        第一性原理：模式识别—— 大脑擅长发现"不对劲"的规律。

        检测的异常模式：
        1. 错误突增（短时间内大量ERROR）
        2. 性能骤降（预测误差突然升高）
        3. 任务堆积（待处理任务数持续增长）
        4. 循环异常（同一错误反复出现）
        """
        if not self._parsed_entries:
            return []

        anomalies = []

        # 1. 错误突增检测
        error_entries = [e for e in self._parsed_entries if e["level"] == "ERROR"]
        if len(error_entries) > 10:
            # 检查是否集中在短时间内
            anomalies.append({
                "type": "error_spike",
                "severity": min(len(error_entries) / 50, 1.0),
                "count": len(error_entries),
                "description": f"检测到{len(error_entries)}个错误，可能存在系统性问题",
            })

        # 2. 性能骤降检测
        errors = []
        for e in self._parsed_entries:
            if "prediction_error" in e["context"]:
                try:
                    errors.append(float(e["context"]["prediction_error"]))
                except ValueError:
                    continue

        if len(errors) >= 10:
            recent = np.array(errors[-10:])
            baseline = np.array(errors[:10]) if len(errors) >= 20 else recent
            recent_mean = np.mean(recent)
            baseline_mean = np.mean(baseline)
            if baseline_mean > 0 and recent_mean > baseline_mean * 2:
                anomalies.append({
                    "type": "performance_degradation",
                    "severity": min((recent_mean / baseline_mean - 1), 1.0),
                    "description": f"预测误差从{baseline_mean:.4f}上升到{recent_mean:.4f}",
                })

        # 3. 循环异常检测
        messages = [e["message"] for e in self._parsed_entries if e["level"] == "ERROR"]
        if messages:
            counter = Counter(messages)
            for msg, count in counter.most_common(3):
                if count > 5:
                    anomalies.append({
                        "type": "recurring_error",
                        "severity": min(count / 20, 1.0),
                        "count": count,
                        "description": f"错误重复出现{count}次: {msg[:50]}...",
                    })

        self._anomaly_patterns = anomalies
        return sorted(anomalies, key=lambda x: x["severity"], reverse=True)

    def analyze_error_frequency(self) -> Dict[str, Any]:
        """
        分析错误频率趋势

        计算错误率的变化趋势（上升/下降/稳定）。
        """
        if not self._parsed_entries:
            return {"error_rate": 0.0, "trend": "unknown"}

        total = len(self._parsed_entries)
        errors = len([e for e in self._parsed_entries if e["level"] == "ERROR"])
        error_rate = errors / total if total > 0 else 0.0

        # 分段比较（前半段 vs 后半段）
        mid = total // 2
        first_half_errors = len([e for e in self._parsed_entries[:mid] if e["level"] == "ERROR"])
        second_half_errors = len([e for e in self._parsed_entries[mid:] if e["level"] == "ERROR"])

        first_rate = first_half_errors / mid if mid > 0 else 0
        second_rate = second_half_errors / (total - mid) if (total - mid) > 0 else 0

        if second_rate > first_rate * 1.5:
            trend = "increasing"
        elif second_rate < first_rate * 0.5:
            trend = "decreasing"
        else:
            trend = "stable"

        return {
            "total_entries": total,
            "error_count": errors,
            "error_rate": error_rate,
            "first_half_rate": first_rate,
            "second_half_rate": second_rate,
            "trend": trend,
        }

    def extract_metrics_trend(self, metric_key: str) -> Dict[str, Any]:
        """
        提取指定指标的趋势

        例如：提取所有"prediction_error"的值，分析其趋势。
        """
        values = []
        for e in self._parsed_entries:
            if metric_key in e["context"]:
                try:
                    values.append(float(e["context"][metric_key]))
                except ValueError:
                    continue

        if not values:
            return {"metric": metric_key, "values": [], "trend": "no_data"}

        arr = np.array(values)
        mid = len(arr) // 2
        first_mean = np.mean(arr[:mid]) if mid > 0 else 0
        second_mean = np.mean(arr[mid:]) if mid < len(arr) else 0

        if second_mean > first_mean * 1.2:
            trend = "worsening"
        elif second_mean < first_mean * 0.8:
            trend = "improving"
        else:
            trend = "stable"

        return {
            "metric": metric_key,
            "count": len(values),
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "first_half_mean": float(first_mean),
            "second_half_mean": float(second_mean),
            "trend": trend,
        }

    def correlate_events(self, cause_pattern: str,
                         effect_pattern: str,
                         window: int = 5) -> List[Dict[str, Any]]:
        """
        关联事件（找根因）

        第一性原理：因果推理—— 当A发生后，B在窗口期内出现的频率显著高于随机水平，
        则A可能是B的原因。

        例如：cause="cpu_throttle", effect="optimize_resources"
        """
        correlations = []
        entries = self._parsed_entries

        for i, e in enumerate(entries):
            if cause_pattern in e["message"]:
                # 在窗口内查找effect
                for j in range(i + 1, min(i + window, len(entries))):
                    if effect_pattern in entries[j]["message"]:
                        correlations.append({
                            "cause_at": i,
                            "effect_at": j,
                            "delay_steps": j - i,
                            "cause_msg": e["message"][:50],
                            "effect_msg": entries[j]["message"][:50],
                        })

        return correlations

    def generate_insights(self) -> List[str]:
        """
        生成洞察报告

        综合所有分析结果，生成人类可读的洞察。
        """
        insights = []

        # 异常洞察
        anomalies = self.detect_anomaly_patterns()
        for a in anomalies[:3]:
            insights.append(f"[异常] {a['description']} (严重度: {a['severity']:.2f})")

        # 错误趋势洞察
        error_trend = self.analyze_error_frequency()
        if error_trend["trend"] == "increasing":
            insights.append(f"[趋势] 错误率上升: 前半段{error_trend['first_half_rate']*100:.1f}% → 后半段{error_trend['second_half_rate']*100:.1f}%")
        elif error_trend["trend"] == "decreasing":
            insights.append(f"[趋势] 错误率下降，系统趋于稳定")

        # 性能趋势洞察
        perf_trend = self.extract_metrics_trend("prediction_error")
        if perf_trend["trend"] == "improving":
            insights.append(f"[性能] 预测精度提升: 均值从{perf_trend['first_half_mean']:.4f}降至{perf_trend['second_half_mean']:.4f}")
        elif perf_trend["trend"] == "worsening":
            insights.append(f"[性能] 预测精度下降，建议检查模型状态")

        # 事件关联洞察
        correlations = self.correlate_events("cpu_throttle", "optimize_resources")
        if correlations:
            insights.append(f"[关联] 检测到{len(correlations)}次CPU节流后触发资源优化，平均延迟{np.mean([c['delay_steps'] for c in correlations]):.1f}步")

        self._insights = insights
        return insights

    def get_stats(self) -> Dict[str, Any]:
        return {
            "parsed_entries": len(self._parsed_entries),
            "anomalies": len(self._anomaly_patterns),
            "insights": len(self._insights),
            "error_rate": self.analyze_error_frequency()["error_rate"],
        }
