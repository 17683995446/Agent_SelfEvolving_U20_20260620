"""
配置校验器。

对加载的配置进行结构校验，提供友好的错误信息。

第一性原理：
- 生物免疫系统在病原体进入前进行筛查——配置在应用前必须校验
- 早失败原则：错误配置越早发现，修复成本越低
- 错误信息应可操作：告诉用户哪里错了、期望什么、如何修复

设计要点：
- 类型校验：每个配置项有期望类型
- 范围校验：数值配置有合理范围
- 依赖校验：配置项间的约束关系
- 友好报错：错误信息包含配置键、当前值、期望值、修复建议
"""

from typing import Any, Dict, List, Optional, Tuple

from agent_core.common.logger import get_logger


# 配置项规范：(键名, 类型, 最小值, 最大值, 是否必需, 描述)
_CONFIG_SPEC: List[Tuple[str, type, Optional[float], Optional[float], bool, str]] = [
    ("app_name", str, None, None, True, "应用名称"),
    ("app_version", str, None, None, True, "应用版本"),
    ("log_level", str, None, None, True, "日志级别(DEBUG/INFO/WARNING/ERROR/CRITICAL)"),
    ("online_interval_seconds", (int, float), 0.01, 86400.0, True, "在线循环间隔(秒)"),
    ("offline_interval_seconds", (int, float), 0.01, 604800.0, True, "离线循环间隔(秒)"),
    ("memory_capacity", int, 1, 10000000, True, "记忆容量"),
    ("exploration_rate", (int, float), 0.0, 1.0, True, "探索率(0-1)"),
    ("epsilon", (int, float), 0.0, 1.0, True, "epsilon-greedy参数(0-1)"),
    ("interrupt_threshold", (int, float), 0.0, 1.0, True, "中断阈值(0-1)"),
    ("feature_dimensions", int, 1, 10000, True, "特征维度"),
    ("low_alpha_init", (int, float), 0.0, 1.0, True, "低层预测器初始学习率"),
    ("low_alpha_min", (int, float), 0.0, 1.0, True, "低层预测器最小学习率"),
    ("low_alpha_max", (int, float), 0.0, 1.0, True, "低层预测器最大学习率"),
    ("low_adaptation_rate", (int, float), 0.0, 1.0, True, "低层自适应率"),
    ("mid_window_size", int, 1, 10000, True, "中层窗口大小"),
    ("mid_forecast_horizon", int, 1, 1000, True, "中层预测范围"),
    ("high_window_size", int, 1, 100000, True, "高层窗口大小"),
    ("high_reversion_strength", (int, float), 0.0, 1.0, True, "高层回归强度"),
    ("ensemble_beta", (int, float), 0.0, 100.0, True, "集成beta参数"),
    ("cpu_interval_seconds", (int, float), 0.1, 3600.0, True, "CPU采样间隔(秒)"),
    ("max_log_lines", int, 1, 1000000, True, "最大日志行数"),
    ("query_page_size", int, 1, 10000, True, "查询页大小"),
    ("batch_query_limit", int, 1, 1000000, True, "批量查询上限"),
]

# 日志级别合法值
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

# 依赖约束：(键A, 键B, 约束描述, 校验函数)
_DEPENDENCY_CHECKS: List[Tuple[str, str, str, Any]] = [
    (
        "low_alpha_min", "low_alpha_max",
        "low_alpha_min must be <= low_alpha_max",
        lambda a, b: a <= b,
    ),
    (
        "low_alpha_init", "low_alpha_max",
        "low_alpha_init must be <= low_alpha_max",
        lambda a, b: a <= b,
    ),
    (
        "low_alpha_init", "low_alpha_min",
        "low_alpha_init must be >= low_alpha_min",
        lambda a, b: a >= b,
    ),
]


class ConfigValidationError(Exception):
    """配置校验错误。"""

    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        super().__init__(f"Config validation failed with {len(errors)} errors:\n" +
                         "\n".join(f"  - {e}" for e in errors))


class ConfigValidator:
    """
    配置校验器。

    校验配置字典的结构完整性与值合理性。
    """

    def __init__(self) -> None:
        self._logger = get_logger()

    def validate(self, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        校验配置。

        Args:
            config: 待校验的配置字典。

        Returns:
            (是否通过, 错误信息列表)
        """
        errors: List[str] = []

        # 检查必需键
        for key, _, _, _, required, desc in _CONFIG_SPEC:
            if required and key not in config:
                errors.append(
                    f"Missing required config '{key}' ({desc}). "
                    f"Add it to your config file."
                )

        # 类型与范围校验
        for key, expected_type, min_val, max_val, _, desc in _CONFIG_SPEC:
            if key not in config:
                continue
            value = config[key]

            # 类型校验
            if not isinstance(value, expected_type):
                type_name = (
                    expected_type.__name__
                    if isinstance(expected_type, type)
                    else " or ".join(t.__name__ for t in expected_type)
                )
                errors.append(
                    f"Config '{key}' has wrong type: "
                    f"expected {type_name}, got {type(value).__name__}. "
                    f"Description: {desc}"
                )
                continue

            # 范围校验（仅数值类型）
            if isinstance(value, bool):
                continue  # bool是int子类，跳过
            if isinstance(value, (int, float)) and min_val is not None:
                if value < min_val:
                    errors.append(
                        f"Config '{key}' value {value} is below minimum {min_val}. "
                        f"Description: {desc}"
                    )
            if isinstance(value, (int, float)) and max_val is not None:
                if value > max_val:
                    errors.append(
                        f"Config '{key}' value {value} exceeds maximum {max_val}. "
                        f"Description: {desc}"
                    )

        # 日志级别校验
        if "log_level" in config:
            level = config["log_level"]
            if isinstance(level, str) and level.upper() not in _VALID_LOG_LEVELS:
                errors.append(
                    f"Config 'log_level' value '{level}' is invalid. "
                    f"Valid values: {sorted(_VALID_LOG_LEVELS)}"
                )

        # 依赖约束校验
        for key_a, key_b, desc, check_fn in _DEPENDENCY_CHECKS:
            if key_a in config and key_b in config:
                try:
                    if not check_fn(config[key_a], config[key_b]):
                        errors.append(
                            f"Config constraint violated: {desc} "
                            f"(got {key_a}={config[key_a]}, {key_b}={config[key_b]})"
                        )
                except TypeError:
                    pass  # 类型错误已在上面报告

        # base_weights 校验
        if "base_weights" in config:
            weights = config["base_weights"]
            if not isinstance(weights, dict):
                errors.append(
                    "Config 'base_weights' must be a dict with 'safety', 'gain', 'efficiency' keys"
                )
            else:
                required_weight_keys = {"safety", "gain", "efficiency"}
                missing = required_weight_keys - set(weights.keys())
                if missing:
                    errors.append(
                        f"Config 'base_weights' missing keys: {missing}. "
                        f"Required: {required_weight_keys}"
                    )
                else:
                    total = sum(weights.values())
                    if abs(total - 1.0) > 0.05:
                        errors.append(
                            f"Config 'base_weights' values must sum to 1.0, "
                            f"got {total:.3f}. "
                            f"Adjust safety/gain/efficiency weights."
                        )

        return (len(errors) == 0, errors)

    def validate_or_raise(self, config: Dict[str, Any]) -> None:
        """校验配置，失败时抛出异常。"""
        ok, errors = self.validate(config)
        if not ok:
            raise ConfigValidationError(errors)

    def get_defaults(self) -> Dict[str, Any]:
        """获取默认配置（从spec推导）。"""
        defaults: Dict[str, Any] = {}
        for key, _, min_val, max_val, _, _ in _CONFIG_SPEC:
            # 使用最小值或合理默认
            if min_val is not None and max_val is not None:
                defaults[key] = min_val
            elif min_val is not None:
                defaults[key] = min_val
        defaults["log_level"] = "INFO"
        defaults["app_name"] = "self_evolving_agent"
        defaults["app_version"] = "1.0.0"
        defaults["base_weights"] = {
            "safety": 0.4,
            "gain": 0.4,
            "efficiency": 0.2,
        }
        defaults["disk_paths"] = ["/"]
        defaults["log_paths"] = []
        return defaults


def validate_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """便捷函数：校验配置。"""
    validator = ConfigValidator()
    return validator.validate(config)
