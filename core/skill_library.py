"""
技能库与技能习得（阶段2：从固定动作到可扩展技能）

第一性原理：生物的技能习得遵循"练习→巩固→迁移"三阶段：
  - 练习：生成技能代码并测试验证
  - 巩固：通过验证的技能入库，可重复调用
  - 迁移：已有技能可被组合调用，解决新问题

SkillLibrary 实现：
  1. register() — 注册新技能（含代码+验证）
  2. validate() — 验证技能代码（语法检查+测试运行）
  3. invoke() — 调用技能
  4. learn_from_requirement() — 从需求描述生成并习得技能
  5. 技能持久化到 data/skills/ 目录（每个技能一个.py文件）
  6. 版本管理 + 成功率追踪

与agent.py的关系：
  - agent.learn_skill(description) — 习得新技能
  - agent.use_skill(name, **kwargs) — 调用技能
  - agent.get_skill_status() — 技能库状态
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from core.interfaces import ISkillLibrary


@dataclass
class Skill:
    """技能定义"""
    name: str                          # 技能名（唯一标识，snake_case）
    description: str                   # 技能描述
    code: str                          # 技能代码（含一个 execute(**kwargs) 函数）
    version: int = 1                   # 版本号
    validated: bool = False            # 是否已通过验证
    created_at: float = field(default_factory=time.time)
    last_used: float = 0.0             # 最后调用时间戳
    invoke_count: int = 0              # 总调用次数
    success_count: int = 0             # 成功调用次数
    failure_count: int = 0             # 失败调用次数
    avg_duration_ms: float = 0.0       # 平均调用耗时
    metadata: Dict[str, Any] = field(default_factory=dict)

    def success_rate(self) -> float:
        """成功率"""
        if self.invoke_count == 0:
            return 0.0
        return self.success_count / self.invoke_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "validated": self.validated,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "invoke_count": self.invoke_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": self.success_rate(),
            "avg_duration_ms": self.avg_duration_ms,
        }


class SkillLibrary(ISkillLibrary):
    """
    技能库

    核心方法（<=7个）：
    1. register() — 注册技能
    2. validate() — 验证技能代码
    3. invoke() — 调用技能
    4. learn_from_requirement() — 从需求生成并习得技能
    5. get_skill() — 查询技能
    6. list_skills() — 列出所有技能
    7. get_stats() — 统计
    """

    def __init__(self,
                 skills_dir: str = "./data/skills",
                 max_skills: int = 100,
                 logger=None,
                 auto_load: bool = True):
        """
        Args:
            skills_dir: 技能文件持久化目录
            max_skills: 最大技能数（防止无限增长）
            logger: 日志器
            auto_load: 是否在构造时自动从磁盘加载已有技能（秩序化阶段1：
                       默认True用于生产兼容；测试设False避免加载污染数据）
        """
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.max_skills = max_skills
        self.logger = logger
        self._skills: Dict[str, Skill] = {}
        # 已加载的技能模块缓存（name → module）
        self._loaded_modules: Dict[str, Any] = {}
        # 全局计数器
        self._total_validations = 0
        self._total_validated_ok = 0
        self._total_invocations = 0
        self._total_invoke_success = 0

        # 加载已有技能（可禁用以避免构造时副作用）
        if auto_load:
            self._load_from_disk()

    def register(self,
                 name: str,
                 description: str,
                 code: str,
                 auto_validate: bool = True) -> Dict[str, Any]:
        """
        注册新技能

        第一性原理：技能注册 = "练习"阶段。生成的代码需要通过验证才能入库。

        Args:
            name: 技能名（snake_case）
            description: 技能描述
            code: 技能代码（必须包含 execute(**kwargs) 函数）
            auto_validate: 是否自动验证

        Returns:
            {"success": bool, "validated": bool, "reason": str}
        """
        # 名称规范检查
        if not name or not name.replace("_", "").isalnum():
            return {"success": False, "validated": False, "reason": "技能名必须为snake_case字母数字"}

        # 容量限制
        if name not in self._skills and len(self._skills) >= self.max_skills:
            # 淘汰成功率最低且最少使用的技能
            self._evict_worst_skill()

        # 版本管理：如果已存在，版本+1
        version = 1
        if name in self._skills:
            version = self._skills[name].version + 1

        skill = Skill(
            name=name,
            description=description,
            code=code,
            version=version,
        )

        # 自动验证
        if auto_validate:
            validation = self.validate(skill)
            skill.validated = validation["valid"]
            if not validation["valid"]:
                return {
                    "success": False,
                    "validated": False,
                    "reason": f"验证失败: {validation['reason']}",
                }

        # 注册入库
        self._skills[name] = skill
        # 清除旧的模块缓存
        if name in self._loaded_modules:
            del self._loaded_modules[name]
        # 持久化
        self._persist_skill(skill)

        if self.logger:
            self.logger.info(f"Skill registered: {name} v{version} (validated={skill.validated})")

        return {"success": True, "validated": skill.validated, "reason": "注册成功", "version": version}

    def validate(self, skill: Skill) -> Dict[str, Any]:
        """
        验证技能代码

        第一性原理：技能必须通过"练习"验证才能巩固入库。
        验证流程：
            1. 语法检查（compile）
            2. 加载模块
            3. 检查 execute 函数存在
            4. 试运行 execute() 空调用

        Returns:
            {"valid": bool, "reason": str}
        """
        self._total_validations += 1

        # 1. 语法检查
        try:
            compile(skill.code, f"<skill_{skill.name}>", "exec")
        except SyntaxError as e:
            return {"valid": False, "reason": f"语法错误: {e}"}

        # 2. 加载模块
        try:
            module = self._load_module(skill)
        except Exception as e:
            return {"valid": False, "reason": f"模块加载失败: {e}"}

        # 3. 检查 execute 函数
        if not hasattr(module, "execute"):
            return {"valid": False, "reason": "缺少 execute 函数"}
        if not callable(module.execute):
            return {"valid": False, "reason": "execute 不是可调用对象"}

        # 4. 试运行（空调用，捕获异常）
        try:
            module.execute()
        except TypeError:
            # execute 可能需要参数，这是允许的
            pass
        except Exception as e:
            return {"valid": False, "reason": f"试运行失败: {e}"}

        self._total_validated_ok += 1
        return {"valid": True, "reason": "验证通过"}

    def invoke(self, name: str, **kwargs) -> Dict[str, Any]:
        """
        调用技能

        第一性原理：技能调用 = "巩固"阶段。每次成功调用强化技能，
        失败调用降低成功率，长期低成功率的技能会被淘汰。

        Args:
            name: 技能名
            **kwargs: 传给 execute 的参数

        Returns:
            {"success": bool, "result": Any, "duration_ms": float, "error": str}
        """
        if name not in self._skills:
            return {"success": False, "result": None, "duration_ms": 0, "error": f"技能 {name} 不存在"}

        skill = self._skills[name]
        self._total_invocations += 1
        skill.invoke_count += 1

        start = time.time()
        try:
            # 加载模块（有缓存）
            if name not in self._loaded_modules:
                self._loaded_modules[name] = self._load_module(skill)
            module = self._loaded_modules[name]

            result = module.execute(**kwargs)
            duration_ms = (time.time() - start) * 1000

            # 更新统计
            skill.success_count += 1
            self._total_invoke_success += 1
            skill.last_used = time.time()
            skill.avg_duration_ms = (
                (skill.avg_duration_ms * (skill.success_count - 1) + duration_ms)
                / skill.success_count
            )

            return {"success": True, "result": result, "duration_ms": duration_ms, "error": None}

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            skill.failure_count += 1
            skill.last_used = time.time()
            error_msg = f"{type(e).__name__}: {e}"
            if self.logger:
                self.logger.error(f"Skill invoke failed: {name} - {error_msg}")
            return {"success": False, "result": None, "duration_ms": duration_ms, "error": error_msg}

    def learn_from_requirement(self,
                               requirement: str,
                               skill_name: Optional[str] = None) -> Dict[str, Any]:
        """
        从需求描述生成并习得技能

        第一性原理：技能"迁移"——从自然语言需求生成可执行技能。
        基于关键词匹配生成技能代码模板，验证通过后入库。

        Args:
            requirement: 需求描述（自然语言）
            skill_name: 指定技能名，None则自动从需求提取

        Returns:
            {"success": bool, "skill_name": str, "reason": str}
        """
        # 生成技能名
        if skill_name is None:
            skill_name = self._extract_skill_name(requirement)
        if not skill_name:
            return {"success": False, "skill_name": "", "reason": "无法从需求提取技能名"}

        # 生成技能代码
        code = self._generate_skill_code(skill_name, requirement)
        description = requirement[:200]

        # 注册（含验证）
        result = self.register(
            name=skill_name,
            description=description,
            code=code,
            auto_validate=True,
        )

        return {
            "success": result["success"],
            "skill_name": skill_name if result["success"] else "",
            "reason": result["reason"],
            "validated": result.get("validated", False),
        }

    def get_skill(self, name: str) -> Optional[Skill]:
        """查询技能"""
        return self._skills.get(name)

    def list_skills(self) -> List[Dict[str, Any]]:
        """列出所有技能"""
        return [s.to_dict() for s in self._skills.values()]

    def get_stats(self) -> Dict[str, Any]:
        """统计"""
        return {
            "total_skills": len(self._skills),
            "validated_skills": sum(1 for s in self._skills.values() if s.validated),
            "total_validations": self._total_validations,
            "total_validated_ok": self._total_validated_ok,
            "total_invocations": self._total_invocations,
            "total_invoke_success": self._total_invoke_success,
            "invoke_success_rate": (
                self._total_invoke_success / self._total_invocations
                if self._total_invocations > 0 else 0.0
            ),
        }

    # ========================================================================
    # 内部方法
    # ========================================================================

    def _load_module(self, skill: Skill):
        """从技能代码加载Python模块"""
        module_name = f"skill_{skill.name}_v{skill.version}"
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        # 执行代码定义模块
        exec(compile(skill.code, f"<skill_{skill.name}>", "exec"), module.__dict__)
        return module

    def _persist_skill(self, skill: Skill) -> None:
        """持久化技能到文件"""
        try:
            skill_file = self.skills_dir / f"{skill.name}.py"
            # 在文件头部添加技能元数据注释
            header = f'"""\n技能: {skill.name}\n描述: {skill.description}\n版本: v{skill.version}\n创建: {time.ctime(skill.created_at)}\n"""\n\n'
            skill_file.write_text(header + skill.code, encoding="utf-8")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to persist skill {skill.name}: {e}")

    def _load_from_disk(self) -> None:
        """从磁盘加载已有技能"""
        try:
            for skill_file in self.skills_dir.glob("*.py"):
                if skill_file.name.startswith("__"):
                    continue
                name = skill_file.stem
                code = skill_file.read_text(encoding="utf-8")
                # 去除头部注释提取真实代码
                if code.startswith('"""'):
                    end = code.find('"""', 3)
                    if end != -1:
                        code = code[end + 3:].strip()

                skill = Skill(
                    name=name,
                    description=f"从磁盘加载的技能",
                    code=code,
                    validated=False,
                )
                # 重新验证
                validation = self.validate(skill)
                skill.validated = validation["valid"]
                self._skills[name] = skill
        except Exception:
            pass

    def _evict_worst_skill(self) -> None:
        """淘汰成功率最低且最少使用的技能"""
        if not self._skills:
            return
        # 按 (成功率, 调用次数) 排序，淘汰最差的
        worst = min(self._skills.values(), key=lambda s: (s.success_rate(), s.invoke_count))
        if worst.name in self._skills:
            del self._skills[worst.name]
            # 删除文件
            try:
                skill_file = self.skills_dir / f"{worst.name}.py"
                if skill_file.exists():
                    skill_file.unlink()
            except Exception:
                pass

    def _extract_skill_name(self, requirement: str) -> str:
        """从需求描述提取技能名"""
        import re
        # 尝试匹配 "xxx技能" 或 "技能xxx"
        match = re.search(r'([a-zA-Z_]\w*)\s*技能', requirement)
        if match:
            return match.group(1).lower()
        match = re.search(r'技能\s*([a-zA-Z_]\w*)', requirement)
        if match:
            return match.group(1).lower()
        # 尝试匹配英文单词
        words = re.findall(r'[a-zA-Z_]\w*', requirement)
        if words:
            return words[0].lower()
        return ""

    def _generate_skill_code(self, name: str, requirement: str) -> str:
        """
        根据需求生成技能代码

        基于关键词匹配生成不同类型的技能模板：
        - "计算"/"compute" → 计算类技能
        - "检查"/"check" → 检查类技能
        - "统计"/"stats" → 统计类技能
        - "转换"/"convert" → 转换类技能
        - 其他 → 通用技能
        """
        req_lower = requirement.lower()

        if "计算" in requirement or "compute" in req_lower or "calculate" in req_lower:
            return self._template_compute(name, requirement)
        elif "检查" in requirement or "check" in req_lower or "detect" in req_lower:
            return self._template_check(name, requirement)
        elif "统计" in requirement or "stats" in req_lower or "count" in req_lower:
            return self._template_stats(name, requirement)
        elif "转换" in requirement or "convert" in req_lower or "transform" in req_lower:
            return self._template_convert(name, requirement)
        else:
            return self._template_generic(name, requirement)

    def _template_compute(self, name: str, requirement: str) -> str:
        """计算类技能模板"""
        return f'''def execute(x=0, y=0, **kwargs):
    """计算技能: {requirement[:100]}"""
    return x + y
'''

    def _template_check(self, name: str, requirement: str) -> str:
        """检查类技能模板"""
        return f'''def execute(value=None, threshold=0, **kwargs):
    """检查技能: {requirement[:100]}"""
    if value is None:
        return False
    return value > threshold
'''

    def _template_stats(self, name: str, requirement: str) -> str:
        """统计类技能模板"""
        return f'''def execute(data=None, **kwargs):
    """统计技能: {requirement[:100]}"""
    if data is None:
        data = []
    if not isinstance(data, (list, tuple)):
        data = [data]
    return {{
        "count": len(data),
        "sum": sum(data) if data else 0,
        "avg": sum(data) / len(data) if data else 0,
        "min": min(data) if data else 0,
        "max": max(data) if data else 0,
    }}
'''

    def _template_convert(self, name: str, requirement: str) -> str:
        """转换类技能模板"""
        return f'''def execute(value=None, target_type="str", **kwargs):
    """转换技能: {requirement[:100]}"""
    if value is None:
        return None
    converters = {{
        "str": str,
        "int": int,
        "float": float,
        "list": list,
        "bool": bool,
    }}
    converter = converters.get(target_type, str)
    try:
        return converter(value)
    except (ValueError, TypeError):
        return value
'''

    def _template_generic(self, name: str, requirement: str) -> str:
        """通用技能模板"""
        return f'''def execute(**kwargs):
    """通用技能: {requirement[:100]}"""
    return {{"status": "ok", "skill": "{name}", "input": kwargs}}
'''
