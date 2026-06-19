"""
PPO训练模块测试。

覆盖：轨迹记录、优势计算、PPO损失、策略更新、清空。
"""

import numpy as np
import pytest

from agent_core.task.ppo_trainer import PPOTrainer


class TestPPOTrainer:
    """PPOTrainer测试类。"""

    @pytest.fixture
    def trainer(self):
        """创建PPO训练器实例。"""
        return PPOTrainer()

    def test_record_step(self, trainer):
        """测试记录步骤。"""
        trainer.record_step(
            state=np.array([1.0]),
            action=np.array([0.5]),
            reward=1.0,
            value=0.5,
            log_prob=-0.2,
        )
        assert trainer.get_trajectory_length() == 1

    def test_compute_advantages(self, trainer):
        """测试优势计算。"""
        trainer.record_step(np.array([1.0]), np.array([0.5]), 1.0, 0.5, -0.2)
        trainer.record_step(np.array([2.0]), np.array([0.6]), 1.0, 0.6, -0.3)
        advantages = trainer.compute_advantages()
        assert len(advantages) == 2
        assert advantages[0] != 0.0

    def test_compute_ppo_loss_clipping(self, trainer):
        """测试PPO裁剪损失。"""
        loss = trainer.compute_ppo_loss(-0.2, 0.5, 1.0)
        assert loss > 0.0

    def test_update_policy(self, trainer):
        """测试策略更新。"""
        trainer.record_step(np.array([1.0]), np.array([0.5]), 1.0, 0.5, -0.2)
        stats = trainer.update_policy(None)
        assert "loss" in stats
        assert trainer.get_trajectory_length() == 0

    def test_clear_trajectory(self, trainer):
        """测试清空轨迹。"""
        trainer.record_step(np.array([1.0]), np.array([0.5]), 1.0, 0.5, -0.2)
        trainer.clear_trajectory()
        assert trainer.get_trajectory_length() == 0
