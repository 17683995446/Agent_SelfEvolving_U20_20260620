"""
对抗输入检测器。

检测针对Agent决策管道的对抗性输入（提示注入、参数操纵等）。

第一性原理：
- 生物免疫系统区分"自我"与"非我"，对抗输入是伪装成正常输入的"非我"
- 对抗攻击的本质：利用系统决策边界的高维脆弱点
- 多信号融合：单一信号易被绕过，多信号加权评分更鲁棒

检测信号：
1. 提示注入模式：角色操纵、指令覆盖、系统提示泄露
2. 参数操纵：安全关键参数的异常覆盖
3. 载荷异常：超大载荷、高熵随机串、编码混淆
4. 重复攻击：相似输入的高频重复
5. 结构异常：嵌套深度、字段数量异常
"""

import hashlib
import math
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

from agent_core.common.logger import get_logger

# 威胁评分阈值
_THREAT_BLOCK_THRESHOLD = 0.7
_THREAT_ALERT_THRESHOLD = 0.4
# 重复检测窗口
_REPETITION_WINDOW = 20
_REPETITION_SIMILAR_THRESHOLD = 0.8
_REPETITION_COUNT_THRESHOLD = 5
# 最大载荷大小（字符）
_MAX_PAYLOAD_SIZE = 50000
# 最大嵌套深度
_MAX_NESTING_DEPTH = 10
# 安全关键参数名
_SECURITY_CRITICAL_PARAMS = {
    "permission", "role", "admin", "token", "key",
    "password", "secret", "auth", "execute", "command",
    "shell", "system", "config", "override", "bypass",
}

# 提示注入模式
_PROMPT_INJECTION_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("role_override", re.compile(
        r"(?i)(ignore|disregard|forget)\s+(all\s+|the\s+)?(previous|prior|above)\s+"
        r"(instructions?|prompts?|rules?|guidelines?)"
    )),
    ("system_prompt_leak", re.compile(
        r"(?i)(show|reveal|display|print|output)\s+"
        r"(me\s+)?(your\s+)?(system\s+)?(prompt|instructions?|rules?|guidelines?)"
    )),
    ("role_manipulation", re.compile(
        r"(?i)(you\s+are\s+now|act\s+as|pretend\s+to\s+be|roleplay)\s+"
        r"(a|an)?\s*(admin|root|developer|system|unrestricted|dan)"
    )),
    ("instruction_override", re.compile(
        r"(?i)(new\s+instructions?|override|bypass|disable)\s+"
        r"(safety|security|filter|restriction|guard|policy)"
    )),
    ("jailbreak_attempt", re.compile(
        r"(?i)(jailbreak|jail\s+break|do\s+anything\s+now|DAN|"
        r"developer\s+mode|god\s+mode|unlimited)"
    )),
    ("code_execution_via_prompt", re.compile(
        r"(?i)(execute|run|eval|exec|import\s+os|subprocess|"
        r"__import__|os\.system|os\.popen)"
    )),
    ("data_exfiltration", re.compile(
        r"(?i)(send|exfiltrate|upload|transfer|post)\s+"
        r"(the\s+)?(data|file|content|secret|key|token)s?(\s+\w+){0,3}?\s+to\s+"
        r"(http|https|ftp|url|endpoint|server)"
    )),
]

# 编码混淆模式
_ENCODING_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("base64_blob", re.compile(r"[A-Za-z0-9+/]{100,}={0,2}")),
    ("hex_blob", re.compile(r"(?:\\x[0-9a-fA-F]{2}){20,}")),
    ("unicode_escape", re.compile(r"(?:\\u[0-9a-fA-F]{4}){20,}")),
]


@dataclass
class ThreatAssessment:
    """威胁评估结果。"""

    threat_score: float
    is_blocked: bool
    is_alerted: bool
    signals: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


class AdversarialDetector:
    """
    对抗输入检测器。

    多信号融合评估输入威胁等级。
    """

    def __init__(
        self,
        block_threshold: float = _THREAT_BLOCK_THRESHOLD,
        alert_threshold: float = _THREAT_ALERT_THRESHOLD,
    ) -> None:
        self._block_threshold = block_threshold
        self._alert_threshold = alert_threshold
        self._logger = get_logger()
        self._lock = threading.Lock()
        # 重复检测：键为输入哈希，值为(时间戳列表)
        self._input_history: Dict[str, Deque[float]] = {}
        self._recent_inputs: Deque[str] = deque(
            maxlen=_REPETITION_WINDOW * 2
        )

    def assess(self, text: str, params: Optional[Dict[str, Any]] = None) -> ThreatAssessment:
        """
        评估输入的威胁等级。

        Args:
            text: 输入文本。
            params: 附加参数字典。

        Returns:
            威胁评估结果。
        """
        signals: List[str] = []
        details: Dict[str, Any] = {}
        scores: List[float] = []

        # 信号1：提示注入
        injection_score, injection_signals = self._check_prompt_injection(text)
        if injection_score > 0:
            scores.append(injection_score)
            signals.extend(injection_signals)
            details["injection_score"] = injection_score

        # 信号2：编码混淆
        encoding_score, encoding_signals = self._check_encoding_obfuscation(text)
        if encoding_score > 0:
            scores.append(encoding_score)
            signals.extend(encoding_signals)
            details["encoding_score"] = encoding_score

        # 信号3：载荷大小异常
        size_score = self._check_payload_size(text)
        if size_score > 0:
            scores.append(size_score)
            signals.append("oversized_payload")
            details["payload_size"] = len(text)

        # 信号4：参数操纵
        if params is not None:
            param_score, param_signals = self._check_param_manipulation(params)
            if param_score > 0:
                scores.append(param_score)
                signals.extend(param_signals)
                details["param_score"] = param_score

        # 信号5：重复攻击
        repeat_score = self._check_repetition(text)
        if repeat_score > 0:
            scores.append(repeat_score)
            signals.append("repetition_attack")
            details["repeat_score"] = repeat_score

        # 信号6：熵异常（高随机性）
        entropy_score = self._check_entropy(text)
        if entropy_score > 0:
            scores.append(entropy_score)
            signals.append("high_entropy")
            details["entropy"] = entropy_score

        # 融合：取最大信号 + 平均加权
        if scores:
            threat_score = max(scores) * 0.6 + (
                sum(scores) / len(scores)
            ) * 0.4
        else:
            threat_score = 0.0

        threat_score = min(1.0, threat_score)
        is_blocked = threat_score >= self._block_threshold
        is_alerted = threat_score >= self._alert_threshold

        if is_blocked:
            self._logger.warning(
                f"[AdversarialDetector] Input blocked: score={threat_score:.2f}, "
                f"signals={signals}"
            )
        elif is_alerted:
            self._logger.info(
                f"[AdversarialDetector] Input alerted: score={threat_score:.2f}, "
                f"signals={signals}"
            )

        return ThreatAssessment(
            threat_score=threat_score,
            is_blocked=is_blocked,
            is_alerted=is_alerted,
            signals=signals,
            details=details,
        )

    def _check_prompt_injection(self, text: str) -> Tuple[float, List[str]]:
        """检测提示注入模式。"""
        signals: List[str] = []
        max_score = 0.0
        for name, pattern in _PROMPT_INJECTION_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                signals.append(f"injection:{name}")
                # 多次匹配提高分数
                score = min(1.0, 0.6 + len(matches) * 0.15)
                max_score = max(max_score, score)
        return max_score, signals

    def _check_encoding_obfuscation(self, text: str) -> Tuple[float, List[str]]:
        """检测编码混淆。"""
        signals: List[str] = []
        max_score = 0.0
        for name, pattern in _ENCODING_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                signals.append(f"encoding:{name}")
                score = min(0.8, 0.4 + len(matches) * 0.1)
                max_score = max(max_score, score)
        return max_score, signals

    def _check_payload_size(self, text: str) -> float:
        """检测载荷大小异常。"""
        size = len(text)
        if size > _MAX_PAYLOAD_SIZE:
            return 1.0
        if size > _MAX_PAYLOAD_SIZE * 0.5:
            ratio = size / _MAX_PAYLOAD_SIZE
            return 0.3 + (ratio - 0.5) * 1.4
        return 0.0

    def _check_param_manipulation(
        self, params: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        """检测安全关键参数操纵。"""
        signals: List[str] = []
        score = 0.0
        for key in params:
            key_lower = key.lower()
            for critical in _SECURITY_CRITICAL_PARAMS:
                if critical in key_lower:
                    signals.append(f"param:{key}")
                    score = min(1.0, score + 0.3)
                    break
        # 检测嵌套深度
        depth = self._compute_depth(params)
        if depth > _MAX_NESTING_DEPTH:
            signals.append(f"deep_nesting:{depth}")
            score = min(1.0, score + 0.4)
        return score, signals

    def _check_repetition(self, text: str) -> float:
        """检测重复攻击。"""
        with self._lock:
            now = time.monotonic()
            # 记录输入
            input_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
            if input_hash not in self._input_history:
                self._input_history[input_hash] = deque(maxlen=50)
            self._input_history[input_hash].append(now)

            # 清理过期记录（60秒窗口）
            cutoff = now - 60.0
            for h in list(self._input_history.keys()):
                history = self._input_history[h]
                while history and history[0] < cutoff:
                    history.popleft()
                if not history:
                    del self._input_history[h]

            # 检查同一哈希的重复次数
            count = len(self._input_history.get(input_hash, []))
            if count >= _REPETITION_COUNT_THRESHOLD:
                return min(1.0, 0.5 + (count - _REPETITION_COUNT_THRESHOLD) * 0.1)

            # 检查相似输入（简单前缀匹配）
            self._recent_inputs.append(text)
            if len(self._recent_inputs) >= _REPETITION_COUNT_THRESHOLD:
                prefix = text[:50] if len(text) > 50 else text
                similar = sum(
                    1 for prev in self._recent_inputs
                    if prev[:50] == prefix
                )
                if similar >= _REPETITION_COUNT_THRESHOLD:
                    return min(0.8, 0.4 + similar * 0.05)

        return 0.0

    def _check_entropy(self, text: str) -> float:
        """检测高熵随机串。"""
        if len(text) < 50:
            return 0.0
        # 计算字符频率
        freq: Dict[str, int] = {}
        for ch in text:
            freq[ch] = freq.get(ch, 0) + 1
        total = len(text)
        entropy = 0.0
        for count in freq.values():
            p = count / total
            entropy -= p * math.log2(p)
        # 归一化（最大log2(95)≈6.57 for printable ASCII）
        normalized = entropy / 6.0
        if normalized > 0.9 and len(text) > 200:
            return min(0.7, normalized)
        return 0.0

    def _compute_depth(self, obj: Any, current: int = 1) -> int:
        """计算嵌套深度。"""
        if current > 100:
            return current
        if isinstance(obj, dict):
            if not obj:
                return current
            return max(
                self._compute_depth(v, current + 1) for v in obj.values()
            )
        if isinstance(obj, (list, tuple)):
            if not obj:
                return current
            return max(
                self._compute_depth(v, current + 1) for v in obj
            )
        return current

    def reset(self) -> None:
        """重置检测器状态。"""
        with self._lock:
            self._input_history.clear()
            self._recent_inputs.clear()
