"""
多模态感知模块。

实现文本、图像、音频的统一感知接口。

第一性原理：
- 不同模态的信息可映射到统一表示空间
- 模态融合提升理解深度
- 缺失模态不应阻断其他模态处理
"""

from typing import Any, Dict, List, Optional

import numpy as np

from agent_core.common.interfaces import ModuleInterface
from agent_core.common.logger import get_logger


class MultimodalPerception(ModuleInterface):
    """
    多模态感知器。

    统一处理文本、图像、音频输入，输出融合特征向量。
    """

    def __init__(self, feature_dim: int = 128) -> None:
        self._feature_dim = feature_dim
        self._logger = get_logger()

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "MultimodalPerception"

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化多模态感知器。"""
        self._logger.info("[MultimodalPerception] Initialized")
        return True

    async def health_check(self) -> Dict[str, Any]:
        """健康检查。"""
        return {"status": "healthy", "metrics": {"feature_dim": self._feature_dim}}

    async def shutdown(self) -> None:
        """优雅关闭。"""
        pass

    def perceive_text(self, text: str) -> np.ndarray:
        """
        处理文本输入。

        Args:
            text: 输入文本。

        Returns:
            文本特征向量。
        """
        seed = sum(ord(c) for c in text) % (2 ** 32)
        rng = np.random.RandomState(seed)
        return rng.randn(self._feature_dim).astype(np.float32)

    def perceive_image(self, image: np.ndarray) -> np.ndarray:
        """
        处理图像输入。

        Args:
            image: 图像数组(H, W, C)。

        Returns:
            图像特征向量。
        """
        flat = image.flatten()[: self._feature_dim]
        if len(flat) < self._feature_dim:
            flat = np.pad(flat, (0, self._feature_dim - len(flat)))
        return (flat / (np.linalg.norm(flat) + 1e-8)).astype(np.float32)

    def perceive_audio(self, audio: np.ndarray) -> np.ndarray:
        """
        处理音频输入。

        Args:
            audio: 音频波形数组。

        Returns:
            音频特征向量。
        """
        spectrogram = np.abs(np.fft.rfft(audio))
        if len(spectrogram) >= self._feature_dim:
            feat = spectrogram[: self._feature_dim]
        else:
            feat = np.pad(spectrogram, (0, self._feature_dim - len(spectrogram)))
        return (feat / (np.linalg.norm(feat) + 1e-8)).astype(np.float32)

    def fuse(
        self,
        features: Dict[str, np.ndarray],
        weights: Optional[Dict[str, float]] = None,
    ) -> np.ndarray:
        """
        融合多模态特征。

        Args:
            features: 各模态特征字典。
            weights: 模态权重字典。

        Returns:
            融合特征向量。
        """
        if not features:
            return np.zeros(self._feature_dim, dtype=np.float32)
        if weights is None:
            weights = {k: 1.0 for k in features}
        total_weight = sum(weights.get(k, 1.0) for k in features)
        fused = np.zeros(self._feature_dim, dtype=np.float32)
        for key, feat in features.items():
            w = weights.get(key, 1.0) / total_weight
            fused += w * feat
        norm = np.linalg.norm(fused)
        if norm > 0:
            fused = fused / norm
        return fused

    def perceive(
        self,
        text: Optional[str] = None,
        image: Optional[np.ndarray] = None,
        audio: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        统一感知入口。

        Args:
            text: 文本输入。
            image: 图像输入。
            audio: 音频输入。

        Returns:
            包含各模态特征和融合特征的字典。
        """
        features: Dict[str, np.ndarray] = {}
        if text is not None:
            features["text"] = self.perceive_text(text)
        if image is not None:
            features["image"] = self.perceive_image(image)
        if audio is not None:
            features["audio"] = self.perceive_audio(audio)
        fused = self.fuse(features)
        return {
            "modalities": features,
            "fused": fused,
            "active_modalities": list(features.keys()),
        }
