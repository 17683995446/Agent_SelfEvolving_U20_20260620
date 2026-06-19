"""
全局常量定义模块。

提供错误码枚举、配置键名枚举与日志级别枚举，
禁止代码中硬编码任何固定值。
"""

from enum import Enum


class ErrorCode(Enum):
    """
    全局错误码枚举。

    接口禁止自定义返回码，所有错误响应必须使用本枚举定义的值。
    """

    SUCCESS = 0
    PARAM_INVALID = 1001
    PARAM_EMPTY = 1002
    PARAM_FORMAT_ERROR = 1003
    PARAM_OUT_OF_RANGE = 1004
    MODULE_NOT_INITIALIZED = 2001
    MODULE_HEALTH_DEGRADED = 2002
    PREDICTION_FAILED = 3001
    TASK_EXECUTION_FAILED = 4001
    RESOURCE_LIMIT_EXCEEDED = 5001
    MEMORY_CAPACITY_FULL = 6001
    SYSTEM_INTERNAL_ERROR = 9001


class EnvironmentConfigKey(Enum):
    """
    环境配置键名枚举。

    配置键名全局统一，禁止私自新增私有配置字段。
    """

    APP_NAME = "app_name"
    APP_VERSION = "app_version"
    LOG_LEVEL = "log_level"
    ONLINE_INTERVAL_SECONDS = "online_interval_seconds"
    OFFLINE_INTERVAL_SECONDS = "offline_interval_seconds"
    MEMORY_CAPACITY = "memory_capacity"
    EXPLORATION_RATE = "exploration_rate"
    EPSILON = "epsilon"
    INTERRUPT_THRESHOLD = "interrupt_threshold"
    FEATURE_DIMENSIONS = "feature_dimensions"
    LOW_ALPHA_INIT = "low_alpha_init"
    LOW_ALPHA_MIN = "low_alpha_min"
    LOW_ALPHA_MAX = "low_alpha_max"
    LOW_ADAPTATION_RATE = "low_adaptation_rate"
    MID_WINDOW_SIZE = "mid_window_size"
    MID_FORECAST_HORIZON = "mid_forecast_horizon"
    HIGH_WINDOW_SIZE = "high_window_size"
    HIGH_REVERSION_STRENGTH = "high_reversion_strength"
    ENSEMBLE_BETA = "ensemble_beta"
    CPU_INTERVAL_SECONDS = "cpu_interval_seconds"
    DISK_PATHS = "disk_paths"
    LOG_PATHS = "log_paths"
    MAX_LOG_LINES = "max_log_lines"
    BASE_WEIGHTS = "base_weights"
    SAFETY_WEIGHT = "safety_weight"
    GAIN_WEIGHT = "gain_weight"
    EFFICIENCY_WEIGHT = "efficiency_weight"
    QUERY_PAGE_SIZE = "query_page_size"
    BATCH_QUERY_LIMIT = "batch_query_limit"


class LogLevel(Enum):
    """
    日志级别枚举。

    日志级别全局固定，禁止自定义日志级别。
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# 分页与批量查询上限全局常量
QUERY_PAGE_SIZE_DEFAULT: int = 20
BATCH_QUERY_LIMIT_DEFAULT: int = 1000

# 数值范围常量
REWARD_MIN_VALUE: float = 0.0
REWARD_MAX_VALUE: float = 1.0
GAP_MIN_VALUE: float = 0.0
GAP_MAX_VALUE: float = 1.0
WEIGHT_SUM_TARGET: float = 1.0
WEIGHT_TOLERANCE: float = 0.01

# 任务执行超时（秒）
TASK_TIMEOUT_SECONDS: float = 300.0

# 驱力缺口阈值
DRIVE_GAP_THRESHOLD: float = 0.2

# 预测误差阈值
PREDICTION_ERROR_THRESHOLD: float = 0.3

# 安全权重紧急阈值
SAFETY_WEIGHT_EMERGENCY: float = 0.6

# 探索-利用平衡默认配置
EXPLORATION_RATE_DEFAULT: float = 0.3
EPSILON_DEFAULT: float = 0.2
INTERRUPT_THRESHOLD_DEFAULT: float = 0.7

# 特征维度默认值
FEATURE_DIMENSIONS_DEFAULT: int = 10

# 记忆容量默认值
MEMORY_CAPACITY_DEFAULT: int = 10000

# 预测器默认配置
LOW_ALPHA_INIT_DEFAULT: float = 0.3
LOW_ALPHA_MIN_DEFAULT: float = 0.05
LOW_ALPHA_MAX_DEFAULT: float = 0.8
LOW_ADAPTATION_RATE_DEFAULT: float = 0.1
MID_WINDOW_SIZE_DEFAULT: int = 20
MID_FORECAST_HORIZON_DEFAULT: int = 5
HIGH_WINDOW_SIZE_DEFAULT: int = 100
HIGH_REVERSION_STRENGTH_DEFAULT: float = 0.3
ENSEMBLE_BETA_DEFAULT: float = 5.0

# 驱力基础权重默认值
BASE_SAFETY_WEIGHT_DEFAULT: float = 0.4
BASE_GAIN_WEIGHT_DEFAULT: float = 0.4
BASE_EFFICIENCY_WEIGHT_DEFAULT: float = 0.2

# CPU采样间隔默认值
CPU_INTERVAL_SECONDS_DEFAULT: float = 1.0

# 日志采样默认值
MAX_LOG_LINES_DEFAULT: int = 100

# 磁盘路径默认值
DISK_PATHS_DEFAULT: list[str] = ["/"]

# 健康度计算权重
HEALTH_CPU_WEIGHT: float = 0.25
HEALTH_MEMORY_WEIGHT: float = 0.25
HEALTH_DISK_WEIGHT: float = 0.25
HEALTH_ERROR_WEIGHT: float = 0.25
