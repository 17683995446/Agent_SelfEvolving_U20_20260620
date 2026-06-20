"""
多层预测器主类模块。

整合底层、中层、高层预测器与集成融合功能。
通过IPredictionModel接口组合层级，支持运行时替换任意层级。
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from agent_core.common.data_contracts import PredictionResult
from agent_core.common.interfaces import IMultiLayerPredictor, IPredictionModel
from agent_core.common.exceptions import ModuleNotInitializedException
from agent_core.common.constants import (
    ENSEMBLE_BETA_DEFAULT,
    FEATURE_DIMENSIONS_DEFAULT,
    HIGH_REVERSION_STRENGTH_DEFAULT,
    HIGH_WINDOW_SIZE_DEFAULT,
    LOW_ADAPTATION_RATE_DEFAULT,
    LOW_ALPHA_INIT_DEFAULT,
    LOW_ALPHA_MAX_DEFAULT,
    LOW_ALPHA_MIN_DEFAULT,
    MID_FORECAST_HORIZON_DEFAULT,
    MID_WINDOW_SIZE_DEFAULT,
)
from agent_core.common.logger import get_logger

from .ensemble import EnsemblePredictor
from .high_level_predictor import MeanReversionPredictor
from .low_level_predictor import AdaptiveExponentialSmoother
from .mid_level_predictor import TrendLinearPredictor


class MultiLayerPredictor(IMultiLayerPredictor):
    """
    多层预测器实现。
    """

    def __init__(self) -> None:
        self._low_predictor: Optional[IPredictionModel] = None
        self._mid_predictor: Optional[IPredictionModel] = None
        self._high_predictor: Optional[IPredictionModel] = None
        self._ensemble: Optional[EnsemblePredictor] = None
        self._config: Dict[str, Any] = {}
        self._initialized = False
        self._logger = get_logger()

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "MultiLayerPredictor"

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化多层预测器。"""
        self._config = config
        dims = config.get("feature_dimensions", FEATURE_DIMENSIONS_DEFAULT)
        self._low_predictor = self._create_low_predictor(config, dims)
        self._mid_predictor = self._create_mid_predictor(config, dims)
        self._high_predictor = self._create_high_predictor(config, dims)
        self._ensemble = EnsemblePredictor(
            feature_dimensions=dims,
            beta=config.get("ensemble_beta", ENSEMBLE_BETA_DEFAULT),
        )
        self._initialized = True
        self._logger.info("[MultiLayerPredictor] Initialized")
        return True

    def _create_low_predictor(
        self, config: Dict[str, Any], dims: int
    ) -> IPredictionModel:
        return AdaptiveExponentialSmoother(
            feature_dimensions=dims,
            alpha_init=config.get("low_alpha_init", LOW_ALPHA_INIT_DEFAULT),
            alpha_min=config.get("low_alpha_min", LOW_ALPHA_MIN_DEFAULT),
            alpha_max=config.get("low_alpha_max", LOW_ALPHA_MAX_DEFAULT),
            adaptation_rate=config.get(
                "low_adaptation_rate", LOW_ADAPTATION_RATE_DEFAULT
            ),
        )

    def _create_mid_predictor(
        self, config: Dict[str, Any], dims: int
    ) -> IPredictionModel:
        return TrendLinearPredictor(
            feature_dimensions=dims,
            window_size=config.get("mid_window_size", MID_WINDOW_SIZE_DEFAULT),
            forecast_horizon=config.get(
                "mid_forecast_horizon", MID_FORECAST_HORIZON_DEFAULT
            ),
        )

    def _create_high_predictor(
        self, config: Dict[str, Any], dims: int
    ) -> IPredictionModel:
        return MeanReversionPredictor(
            feature_dimensions=dims,
            window_size=config.get("high_window_size", HIGH_WINDOW_SIZE_DEFAULT),
            reversion_strength=config.get(
                "high_reversion_strength", HIGH_REVERSION_STRENGTH_DEFAULT
            ),
        )

    def predict_all(self, state: np.ndarray) -> PredictionResult:
        """生成多层预测。"""
        if not self._initialized:
            raise ModuleNotInitializedException(
                "MultiLayerPredictor not initialized"
            )
        state_arr = np.asarray(state, dtype=np.float32)
        expected = self._config.get("feature_dimensions", FEATURE_DIMENSIONS_DEFAULT)
        if state_arr.shape[0] != expected:
            raise ValueError(
                f"Input dimension {state_arr.shape[0]} != expected {expected}"
            )
        # Bug24修复：NaN/inf清洗，避免污染下游所有模块
        if not np.all(np.isfinite(state_arr)):
            state_arr = np.nan_to_num(state_arr, nan=0.0, posinf=1.0, neginf=0.0)
        low_pred = self._low_predictor.predict(state_arr)
        mid_pred = self._mid_predictor.predict(state_arr)
        high_pred = self._high_predictor.predict(state_arr)
        ensemble_pred, confidence = self._ensemble.combine(
            low_pred, mid_pred, high_pred
        )
        return PredictionResult(
            low_level=low_pred,
            mid_level=mid_pred,
            high_level=high_pred,
            ensemble=ensemble_pred,
            confidence=confidence,
        )

    def update_all(self, state: np.ndarray, actual: np.ndarray) -> None:
        """更新所有层级。"""
        if not self._initialized:
            return
        state_arr = np.asarray(state, dtype=np.float32)
        actual_arr = np.asarray(actual, dtype=np.float32)
        self._update_predictors(state_arr, actual_arr)
        self._update_ensemble()

    def _update_predictors(
        self, state: np.ndarray, actual: np.ndarray
    ) -> None:
        self._low_predictor.update(state, actual)
        self._mid_predictor.update(state, actual)
        self._high_predictor.update(state, actual)

    def _update_ensemble(self) -> None:
        errors = {
            "low": self._low_predictor.get_error(),
            "mid": self._mid_predictor.get_error(),
            "high": self._high_predictor.get_error(),
        }
        self._ensemble.update_errors(errors)

    async def health_check(self) -> Dict[str, Any]:
        """健康检查。"""
        if not self._initialized:
            return {"status": "unhealthy", "metrics": {}}
        return {
            "status": "healthy",
            "metrics": {
                "low_error": self._low_predictor.get_error(),
                "mid_error": self._mid_predictor.get_error(),
                "high_error": self._high_predictor.get_error(),
                "layer_errors": self._ensemble._layer_errors.copy(),
            },
        }

    # C-9: 漂移检测统计与置信区间
    def get_drift_stats(self) -> Dict[str, Any]:
        """获取各层漂移检测统计。"""
        if not self._initialized:
            return {}
        return {
            "low": self._low_predictor.get_drift_stats(),
            "mid": self._mid_predictor.get_drift_stats(),
            "high": self._high_predictor.get_drift_stats(),
        }

    def get_confidence_interval(self) -> Tuple[float, float]:
        """C-9: 获取集成预测置信区间。"""
        if not self._initialized or self._ensemble is None:
            return 0.0, 0.0
        return self._ensemble.get_confidence_interval()

    def get_layer_weights(self) -> Dict[str, float]:
        """C-9: 获取当前各层归一化权重。"""
        if not self._initialized or self._ensemble is None:
            return {"low": 1 / 3, "mid": 1 / 3, "high": 1 / 3}
        return self._ensemble.get_layer_weights()

    def swap_layer(self, layer: str, new_predictor: IPredictionModel) -> bool:
        """
        在线替换指定层级预测器。

        Args:
            layer: 层级名称（low/mid/high）。
            new_predictor: 新预测器实例。

        Returns:
            替换成功返回True。
        """
        if layer == "low":
            self._low_predictor = new_predictor
        elif layer == "mid":
            self._mid_predictor = new_predictor
        elif layer == "high":
            self._high_predictor = new_predictor
        else:
            self._logger.error(f"[MultiLayerPredictor] Unknown layer: {layer}")
            return False
        self._logger.info(f"[MultiLayerPredictor] Swapped {layer} layer")
        return True

    async def shutdown(self) -> None:
        """优雅关闭。"""
        self._initialized = False
        self._low_predictor = None
        self._mid_predictor = None
        self._high_predictor = None
        self._ensemble = None
