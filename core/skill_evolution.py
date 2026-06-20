"""
自主技能进化闭环（阶段5：从固定技能到自进化技能）

第一性原理：技能通过"使用→评估→优化→验证→部署"的闭环不断进化。
  - 评估：基于成功率、耗时、结果质量评估技能性能
  - 优化：对低性能技能自动生成改进版本（加错误处理/缓存/参数调优）
  - 验证：新版本必须通过验证才能部署
  - 部署：新版本替换旧版本，保留历史版本供回滚
  - 回滚：新版本性能下降时自动回滚到上一版本

SkillEvolutionEngine 实现：
  1. evaluate() — 评估技能性能
  2. optimize() — 自动优化技能代码
  3. rollback() — 回滚到上一版本
  4. run_evolution_cycle() — 运行一个完整进化周期
  5. get_evolution_history() — 获取进化历史
  6. get_status() — 状态

与SkillLibrary的关系：
  - SkillEvolutionEngine 依赖 SkillLibrary 进行技能注册/验证/调用
  - 每次优化生成新版本，通过 SkillLibrary.register() 入库
  - 回滚时恢复上一版本的代码
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.skill_library import Skill, SkillLibrary
from core.interfaces import ISkillEvolution


@dataclass
class SkillEvaluation:
    """技能评估结果"""
    skill_name: str
    version: int
    success_rate: float
    invoke_count: int
    avg_duration_ms: float
    score: float                          # 综合评分 0-1
    verdict: str                          # "excellent"/"good"/"needs_improvement"/"poor"
    issues: List[str] = field(default_factory=list)


@dataclass
class EvolutionRecord:
    """进化记录"""
    skill_name: str
    timestamp: float
    action: str                           # "evaluate"/"optimize"/"rollback"/"deploy"
    from_version: int
    to_version: int
    from_score: float
    to_score: float
    reason: str = ""


class SkillEvolutionEngine(ISkillEvolution):
    """
    技能进化引擎

    第一性原理：技能通过"使用→评估→优化→验证→部署"的闭环不断进化。
    低性能技能自动优化，新版本性能下降自动回滚。

    核心方法（<=7个）：
    1. evaluate() — 评估技能性能
    2. optimize() — 自动优化技能代码
    3. rollback() — 回滚到上一版本
    4. run_evolution_cycle() — 运行一个完整进化周期
    5. get_evolution_history() — 获取进化历史
    6. get_status() — 状态
    """

    # 评估阈值
    EXCELLENT_THRESHOLD = 0.9
    GOOD_THRESHOLD = 0.7
    POOR_THRESHOLD = 0.3
    # 优化触发条件
    MIN_INVOCATIONS_BEFORE_OPTIMIZE = 3
    # 回滚条件：新版本评分比旧版本低这么多才回滚
    ROLLBACK_DELTA = 0.1

    def __init__(self,
                 skill_library: SkillLibrary,
                 max_history: int = 500,
                 logger=None):
        """
        Args:
            skill_library: 技能库
            max_history: 最大进化历史记录数
            logger: 日志器
        """
        self.skill_library = skill_library
        self.logger = logger
        self.max_history = max_history

        # 进化历史
        self._evolution_history: List[EvolutionRecord] = []
        # 版本代码存档：skill_name → {version → code}
        self._version_archive: Dict[str, Dict[int, str]] = {}
        # 版本评分存档：skill_name → {version → score}
        self._version_scores: Dict[str, Dict[int, float]] = {}

        # 统计
        self._total_evaluations = 0
        self._total_optimizations = 0
        self._total_rollbacks = 0
        self._total_deployments = 0

    # ========================================================================
    # 公开方法
    # ========================================================================

    def evaluate(self, skill_name: str) -> Optional[SkillEvaluation]:
        """
        评估技能性能

        第一性原理：基于"成功率×权重 + 速度×权重"计算综合评分。
        成功率是最重要的指标，速度是次要指标。

        Returns:
            评估结果，技能不存在则返回None
        """
        skill = self.skill_library.get_skill(skill_name)
        if skill is None:
            return None

        self._total_evaluations += 1

        success_rate = skill.success_rate()
        avg_duration = skill.avg_duration_ms

        # 综合评分：成功率(70%) + 速度(30%)
        # 速度评分：耗时越低分越高，100ms=1.0, 1000ms=0.0
        speed_score = max(0.0, 1.0 - (avg_duration / 1000.0)) if avg_duration > 0 else 0.5
        score = success_rate * 0.7 + speed_score * 0.3

        # 评级
        if score >= self.EXCELLENT_THRESHOLD:
            verdict = "excellent"
        elif score >= self.GOOD_THRESHOLD:
            verdict = "good"
        elif score >= self.POOR_THRESHOLD:
            verdict = "needs_improvement"
        else:
            verdict = "poor"

        # 识别问题
        issues = []
        if success_rate < 0.5:
            issues.append("成功率低")
        if avg_duration > 500:
            issues.append("耗时过长")
        if skill.invoke_count < self.MIN_INVOCATIONS_BEFORE_OPTIMIZE:
            issues.append("调用次数不足")

        evaluation = SkillEvaluation(
            skill_name=skill_name,
            version=skill.version,
            success_rate=success_rate,
            invoke_count=skill.invoke_count,
            avg_duration_ms=avg_duration,
            score=score,
            verdict=verdict,
            issues=issues,
        )

        # 记录评分
        if skill_name not in self._version_scores:
            self._version_scores[skill_name] = {}
        self._version_scores[skill_name][skill.version] = score

        # 归档当前版本代码
        if skill_name not in self._version_archive:
            self._version_archive[skill_name] = {}
        self._version_archive[skill_name][skill.version] = skill.code

        # 记录进化历史
        self._record_evolution(
            skill_name=skill_name,
            action="evaluate",
            from_version=skill.version,
            to_version=skill.version,
            from_score=score,
            to_score=score,
            reason=verdict,
        )

        return evaluation

    def optimize(self, skill_name: str) -> Dict[str, Any]:
        """
        自动优化技能代码

        第一性原理：基于评估结果，对技能代码应用优化策略：
        - 成功率低 → 添加错误处理和重试逻辑
        - 耗时长 → 添加结果缓存
        - 结果不准确 → 调整算法参数

        优化后生成新版本，通过验证后部署。

        Returns:
            {"success": bool, "new_version": int, "reason": str}
        """
        skill = self.skill_library.get_skill(skill_name)
        if skill is None:
            return {"success": False, "new_version": 0, "reason": "技能不存在"}

        if skill.invoke_count < self.MIN_INVOCATIONS_BEFORE_OPTIMIZE:
            return {"success": False, "new_version": 0,
                    "reason": f"调用次数不足({skill.invoke_count}<{self.MIN_INVOCATIONS_BEFORE_OPTIMIZE})"}

        old_score = self._version_scores.get(skill_name, {}).get(skill.version, 0.0)
        old_code = skill.code

        # 生成优化代码
        optimized_code = self._apply_optimizations(skill)

        if optimized_code == old_code:
            return {"success": False, "new_version": skill.version,
                    "reason": "无可应用的优化"}

        # 注册新版本（含验证）
        result = self.skill_library.register(
            name=skill_name,
            description=skill.description + " (optimized)",
            code=optimized_code,
            auto_validate=True,
        )

        if not result["success"]:
            return {"success": False, "new_version": skill.version,
                    "reason": f"优化版本验证失败: {result['reason']}"}

        new_version = result["version"]
        self._total_optimizations += 1

        # 归档新版本
        if skill_name not in self._version_archive:
            self._version_archive[skill_name] = {}
        self._version_archive[skill_name][new_version] = optimized_code

        # 记录进化历史
        self._record_evolution(
            skill_name=skill_name,
            action="optimize",
            from_version=skill.version,
            to_version=new_version,
            from_score=old_score,
            to_score=0.0,  # 新版本尚未评估
            reason="auto_optimize",
        )

        if self.logger:
            self.logger.info(
                f"Skill optimized: {skill_name} v{skill.version}→v{new_version}"
            )

        return {"success": True, "new_version": new_version,
                "reason": f"优化成功 v{skill.version}→v{new_version}"}

    def rollback(self, skill_name: str) -> Dict[str, Any]:
        """
        回滚到上一版本

        第一性原理：新版本性能下降时，回滚到已验证的旧版本。

        Returns:
            {"success": bool, "rolled_to_version": int, "reason": str}
        """
        skill = self.skill_library.get_skill(skill_name)
        if skill is None:
            return {"success": False, "rolled_to_version": 0, "reason": "技能不存在"}

        archive = self._version_archive.get(skill_name, {})
        if skill.version <= 1 or (skill.version - 1) not in archive:
            return {"success": False, "rolled_to_version": skill.version,
                    "reason": "无旧版本可回滚"}

        old_version = skill.version - 1
        old_code = archive[old_version]

        # 注册旧版本代码（版本号会+1，但代码是旧的）
        result = self.skill_library.register(
            name=skill_name,
            description=skill.description + f" (rollback to v{old_version})",
            code=old_code,
            auto_validate=True,
        )

        if not result["success"]:
            return {"success": False, "rolled_to_version": skill.version,
                    "reason": f"回滚版本验证失败: {result['reason']}"}

        new_version = result["version"]
        self._total_rollbacks += 1

        # 记录进化历史
        old_score = self._version_scores.get(skill_name, {}).get(skill.version, 0.0)
        rollback_score = self._version_scores.get(skill_name, {}).get(old_version, 0.0)
        self._record_evolution(
            skill_name=skill_name,
            action="rollback",
            from_version=skill.version,
            to_version=new_version,
            from_score=old_score,
            to_score=rollback_score,
            reason=f"rollback_to_v{old_version}",
        )

        if self.logger:
            self.logger.info(
                f"Skill rolled back: {skill_name} v{skill.version}→v{new_version} (code from v{old_version})"
            )

        return {"success": True, "rolled_to_version": new_version,
                "reason": f"回滚到v{old_version}的代码（新版本号v{new_version}）"}

    def run_evolution_cycle(self) -> Dict[str, Any]:
        """
        运行一个完整的进化周期

        第一性原理：进化闭环 = 评估所有技能 → 优化低性能技能 → 评估新版本 → 回滚退化版本

        Returns:
            {"evaluated": int, "optimized": int, "rolled_back": int, "details": list}
        """
        skills = self.skill_library.list_skills()
        evaluated = 0
        optimized = 0
        rolled_back = 0
        details = []

        for skill_info in skills:
            name = skill_info["name"]

            # 1. 评估
            evaluation = self.evaluate(name)
            if evaluation is None:
                continue
            evaluated += 1

            # 2. 需要优化的技能
            if evaluation.verdict in ("needs_improvement", "poor"):
                if evaluation.invoke_count >= self.MIN_INVOCATIONS_BEFORE_OPTIMIZE:
                    opt_result = self.optimize(name)
                    if opt_result["success"]:
                        optimized += 1
                        details.append({
                            "skill": name,
                            "action": "optimized",
                            "from": evaluation.version,
                            "to": opt_result["new_version"],
                        })

                        # 3. 评估新版本（通过试调用）
                        new_eval = self.evaluate(name)
                        if new_eval:
                            # 4. 检查是否需要回滚
                            old_score = evaluation.score
                            new_score = new_eval.score
                            if new_score < old_score - self.ROLLBACK_DELTA:
                                rb_result = self.rollback(name)
                                if rb_result["success"]:
                                    rolled_back += 1
                                    details.append({
                                        "skill": name,
                                        "action": "rolled_back",
                                        "reason": f"score dropped {old_score:.2f}→{new_score:.2f}",
                                    })

        if self.logger:
            self.logger.info(
                f"Evolution cycle: evaluated={evaluated} optimized={optimized} rolled_back={rolled_back}"
            )

        return {
            "evaluated": evaluated,
            "optimized": optimized,
            "rolled_back": rolled_back,
            "details": details,
        }

    def get_evolution_history(self, skill_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取进化历史"""
        records = self._evolution_history
        if skill_name:
            records = [r for r in records if r.skill_name == skill_name]
        return [
            {
                "skill_name": r.skill_name,
                "timestamp": r.timestamp,
                "action": r.action,
                "from_version": r.from_version,
                "to_version": r.to_version,
                "from_score": r.from_score,
                "to_score": r.to_score,
                "reason": r.reason,
            }
            for r in records
        ]

    def get_status(self) -> Dict[str, Any]:
        """进化引擎状态"""
        return {
            "total_evaluations": self._total_evaluations,
            "total_optimizations": self._total_optimizations,
            "total_rollbacks": self._total_rollbacks,
            "total_deployments": self._total_deployments,
            "history_size": len(self._evolution_history),
            "archived_skills": len(self._version_archive),
        }

    # ========================================================================
    # 内部方法
    # ========================================================================

    def _apply_optimizations(self, skill: Skill) -> str:
        """
        应用优化策略到技能代码

        策略：
        1. 成功率低 → 添加try-except错误处理和默认返回值
        2. 耗时长 → 添加简单缓存（基于参数哈希）
        3. 通用 → 添加输入验证
        """
        code = skill.code
        success_rate = skill.success_rate()
        avg_duration = skill.avg_duration_ms

        # 策略1：添加错误处理（成功率低时）
        if success_rate < 0.7 and "try:" not in code:
            code = self._add_error_handling(code, skill.name)

        # 策略2：添加缓存（耗时长时）
        elif avg_duration > 200 and "_cache" not in code:
            code = self._add_caching(code, skill.name)

        # 策略3：添加输入验证（通用）
        elif "if" not in code and "assert" not in code:
            code = self._add_input_validation(code, skill.name)

        return code

    def _add_error_handling(self, code: str, skill_name: str) -> str:
        """添加错误处理：用wrapper包裹原execute，捕获异常返回默认值"""
        if "def execute" not in code:
            return code
        # 把原函数重命名为_original_execute，新execute调用它并捕获异常
        wrapped = code.replace("def execute(", "def _original_execute(", 1)
        wrapper = '''

def execute(**kwargs):
    """优化版：带错误处理"""
    try:
        return _original_execute(**kwargs)
    except Exception:
        return None
'''
        return wrapped + wrapper

    def _add_caching(self, code: str, skill_name: str) -> str:
        """添加结果缓存：用wrapper包裹原execute，缓存结果"""
        if "def execute" not in code:
            return code
        wrapped = code.replace("def execute(", "def _original_execute(", 1)
        cache_wrapper = '''

_cache = {}

def execute(**kwargs):
    """优化版：带缓存"""
    _key = str(sorted(kwargs.items()))
    if _key in _cache:
        return _cache[_key]
    _result = _original_execute(**kwargs)
    _cache[_key] = _result
    return _result
'''
        return wrapped + cache_wrapper

    def _add_input_validation(self, code: str, skill_name: str) -> str:
        """添加输入验证：在函数开头加kwargs默认值"""
        if "def execute" not in code:
            return code
        lines = code.split("\n")
        new_lines = []
        for line in lines:
            if "def execute" in line:
                new_lines.append(line)
                new_lines.append("    if kwargs is None:")
                new_lines.append("        kwargs = {}")
            else:
                new_lines.append(line)
        return "\n".join(new_lines)

    def _record_evolution(self,
                          skill_name: str,
                          action: str,
                          from_version: int,
                          to_version: int,
                          from_score: float,
                          to_score: float,
                          reason: str = "") -> None:
        """记录进化历史"""
        self._evolution_history.append(EvolutionRecord(
            skill_name=skill_name,
            timestamp=time.time(),
            action=action,
            from_version=from_version,
            to_version=to_version,
            from_score=from_score,
            to_score=to_score,
            reason=reason,
        ))
        # 有界历史
        if len(self._evolution_history) > self.max_history:
            self._evolution_history = self._evolution_history[-self.max_history:]
