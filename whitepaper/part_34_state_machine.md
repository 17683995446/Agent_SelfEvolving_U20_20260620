# 第三十四章：状态机与生命周期管理

## 34.1 系统状态机设计

### 34.1.1 状态机概述

自驱永续进化Agent系统采用分层状态机设计，确保系统在各种条件下都能保持可控和可预测的行为。

**状态机层级：**

```
系统级状态机（System State Machine）
├── 运行状态机（Runtime State Machine）
│   ├── 初始化（INITIALIZING）
│   ├── 运行（RUNNING）
│   ├── 空闲（IDLE）
│   ├── 复盘（REVIEWING）
│   └── 错误（ERROR）
├── 安全状态机（Safety State Machine）
│   ├── 正常（NORMAL）
│   ├── 警戒（ALERT）
│   ├── 紧急（EMERGENCY）
│   └── 锁定（LOCKDOWN）
└── 进化状态机（Evolution State Machine）
    ├── 稳定（STABLE）
    ├── 微修正（MICRO_ADJUST）
    ├── 重构（REBUILDING）
    └── 回滚（ROLLING_BACK）
```

### 34.1.2 系统级状态机实现

```python
from enum import Enum, auto
from typing import Dict, List, Callable, Optional
import asyncio

class SystemState(Enum):
    """系统级状态"""
    OFFLINE = auto()           # 离线
    INITIALIZING = auto()      # 初始化中
    READY = auto()             # 就绪
    RUNNING = auto()           # 运行中
    PAUSED = auto()            # 暂停
    SHUTTING_DOWN = auto()     # 关闭中
    SHUTDOWN = auto()          # 已关闭

class RuntimeState(Enum):
    """运行状态"""
    IDLE = auto()              # 空闲
    PERCEIVING = auto()        # 感知中
    COMPUTING_DRIVES = auto()  # 计算驱力
    GENERATING_TASKS = auto()  # 生成任务
    DECIDING = auto()          # 决策中
    EXECUTING = auto()         # 执行中
    PREDICTING = auto()        # 预测中
    LEARNING = auto()          # 学习中
    REVIEWING = auto()         # 复盘中

class SafetyState(Enum):
    """安全状态"""
    NORMAL = auto()            # 正常
    WATCH = auto()             # 观察
    ALERT = auto()             # 警戒
    EMERGENCY = auto()         # 紧急
    LOCKDOWN = auto()          # 锁定

class EvolutionState(Enum):
    """进化状态"""
    STABLE = auto()            # 稳定
    EXPLORING = auto()         # 探索中
    MICRO_ADJUST = auto()      # 微修正
    REBUILDING = auto()        # 重构中
    VALIDATING = auto()        # 验证中
    ROLLING_BACK = auto()      # 回滚中

class StateMachine:
    """
    通用状态机实现
    
    特性：
    - 支持层级状态机
    - 状态转换守卫条件
    - 进入/退出动作
    - 转换动作
    - 历史状态记录
    """
    
    def __init__(self, name: str, initial_state: Enum):
        self.name = name
        self.current_state = initial_state
        self.previous_state = None
        self.state_history = []
        
        # 状态转换规则
        self.transitions: Dict[Enum, Dict[Enum, Dict]] = {}
        
        # 状态动作
        self.entry_actions: Dict[Enum, List[Callable]] = {}
        self.exit_actions: Dict[Enum, List[Callable]] = {}
        self.transition_actions: Dict[Tuple[Enum, Enum], List[Callable]] = {}
        
        # 守卫条件
        self.guards: Dict[Tuple[Enum, Enum], List[Callable]] = {}
        
    def add_transition(
        self,
        from_state: Enum,
        to_state: Enum,
        guard: Optional[Callable] = None,
        action: Optional[Callable] = None
    ):
        """添加状态转换规则"""
        if from_state not in self.transitions:
            self.transitions[from_state] = {}
            
        self.transitions[from_state][to_state] = {
            'guard': guard,
            'action': action
        }
        
    def add_entry_action(self, state: Enum, action: Callable):
        """添加进入状态动作"""
        if state not in self.entry_actions:
            self.entry_actions[state] = []
        self.entry_actions[state].append(action)
        
    def add_exit_action(self, state: Enum, action: Callable):
        """添加退出状态动作"""
        if state not in self.exit_actions:
            self.exit_actions[state] = []
        self.exit_actions[state].append(action)
        
    async def transition(self, to_state: Enum, context: Dict = None) -> bool:
        """
        执行状态转换
        
        Args:
            to_state: 目标状态
            context: 转换上下文
            
        Returns:
            转换是否成功
        """
        from_state = self.current_state
        
        # 检查转换是否允许
        if from_state not in self.transitions or to_state not in self.transitions[from_state]:
            return False
            
        transition_rule = self.transitions[from_state][to_state]
        
        # 检查守卫条件
        if transition_rule['guard'] and not await self._call_guard(transition_rule['guard'], context):
            return False
            
        # 执行退出动作
        if from_state in self.exit_actions:
            for action in self.exit_actions[from_state]:
                await action(context)
                
        # 执行转换动作
        if transition_rule['action']:
            await transition_rule['action'](context)
            
        # 更新状态
        self.previous_state = from_state
        self.current_state = to_state
        self.state_history.append({
            'from': from_state,
            'to': to_state,
            'timestamp': time.time(),
            'context': context
        })
        
        # 执行进入动作
        if to_state in self.entry_actions:
            for action in self.entry_actions[to_state]:
                await action(context)
                
        return True
        
    async def _call_guard(self, guard: Callable, context: Dict) -> bool:
        """调用守卫条件"""
        if asyncio.iscoroutinefunction(guard):
            return await guard(context)
        return guard(context)
        
    def can_transition(self, to_state: Enum) -> bool:
        """检查是否可以转换到目标状态"""
        if self.current_state not in self.transitions:
            return False
        return to_state in self.transitions[self.current_state]
        
    def get_available_transitions(self) -> List[Enum]:
        """获取当前可用的转换目标"""
        if self.current_state not in self.transitions:
            return []
        return list(self.transitions[self.current_state].keys())
```

### 34.1.3 系统级状态机配置

```python
class SystemStateMachine:
    """系统级状态机管理器"""
    
    def __init__(self, agent):
        self.agent = agent
        self.system_sm = StateMachine("System", SystemState.OFFLINE)
        self.runtime_sm = StateMachine("Runtime", RuntimeState.IDLE)
        self.safety_sm = StateMachine("Safety", SafetyState.NORMAL)
        self.evolution_sm = StateMachine("Evolution", EvolutionState.STABLE)
        
        self._setup_system_transitions()
        self._setup_runtime_transitions()
        self._setup_safety_transitions()
        self._setup_evolution_transitions()
        
    def _setup_system_transitions(self):
        """配置系统级状态转换"""
        # OFFLINE -> INITIALIZING
        self.system_sm.add_transition(
            SystemState.OFFLINE, SystemState.INITIALIZING,
            guard=lambda ctx: ctx.get('start_command', False),
            action=self._on_start_initializing
        )
        
        # INITIALIZING -> READY
        self.system_sm.add_transition(
            SystemState.INITIALIZING, SystemState.READY,
            guard=lambda ctx: ctx.get('init_complete', False),
            action=self._on_init_complete
        )
        
        # READY -> RUNNING
        self.system_sm.add_transition(
            SystemState.READY, SystemState.RUNNING,
            guard=lambda ctx: ctx.get('run_command', False),
            action=self._on_start_running
        )
        
        # RUNNING -> PAUSED
        self.system_sm.add_transition(
            SystemState.RUNNING, SystemState.PAUSED,
            guard=lambda ctx: ctx.get('pause_command', False),
            action=self._on_pause
        )
        
        # PAUSED -> RUNNING
        self.system_sm.add_transition(
            SystemState.PAUSED, SystemState.RUNNING,
            guard=lambda ctx: ctx.get('resume_command', False),
            action=self._on_resume
        )
        
        # RUNNING -> SHUTTING_DOWN
        self.system_sm.add_transition(
            SystemState.RUNNING, SystemState.SHUTTING_DOWN,
            guard=lambda ctx: ctx.get('shutdown_command', False),
            action=self._on_shutdown
        )
        
        # SHUTTING_DOWN -> SHUTDOWN
        self.system_sm.add_transition(
            SystemState.SHUTTING_DOWN, SystemState.SHUTDOWN,
            guard=lambda ctx: ctx.get('cleanup_complete', False),
            action=self._on_shutdown_complete
        )
        
        # 任意状态 -> ERROR
        for state in SystemState:
            if state != SystemState.SHUTDOWN:
                self.system_sm.add_transition(
                    state, SystemState.SHUTTING_DOWN,
                    guard=lambda ctx: ctx.get('fatal_error', False),
                    action=self._on_fatal_error
                )
                
    def _setup_runtime_transitions(self):
        """配置运行状态转换"""
        # 主循环状态转换
        states = [
            RuntimeState.IDLE,
            RuntimeState.PERCEIVING,
            RuntimeState.COMPUTING_DRIVES,
            RuntimeState.GENERATING_TASKS,
            RuntimeState.DECIDING,
            RuntimeState.EXECUTING,
            RuntimeState.PREDICTING,
            RuntimeState.LEARNING
        ]
        
        for i in range(len(states) - 1):
            self.runtime_sm.add_transition(
                states[i], states[i + 1],
                guard=lambda ctx, next_state=states[i+1]: ctx.get('next_state') == next_state
            )
            
        # 循环回到IDLE
        self.runtime_sm.add_transition(
            RuntimeState.LEARNING, RuntimeState.IDLE,
            guard=lambda ctx: ctx.get('cycle_complete', False)
        )
        
        # 进入复盘
        self.runtime_sm.add_transition(
            RuntimeState.IDLE, RuntimeState.REVIEWING,
            guard=lambda ctx: ctx.get('review_triggered', False),
            action=self._on_start_review
        )
        
        # 复盘完成
        self.runtime_sm.add_transition(
            RuntimeState.REVIEWING, RuntimeState.IDLE,
            guard=lambda ctx: ctx.get('review_complete', False),
            action=self._on_review_complete
        )
        
    def _setup_safety_transitions(self):
        """配置安全状态转换"""
        # NORMAL -> WATCH
        self.safety_sm.add_transition(
            SafetyState.NORMAL, SafetyState.WATCH,
            guard=lambda ctx: ctx.get('anomaly_detected', False)
        )
        
        # WATCH -> ALERT
        self.safety_sm.add_transition(
            SafetyState.WATCH, SafetyState.ALERT,
            guard=lambda ctx: ctx.get('anomaly_persistent', False)
        )
        
        # ALERT -> EMERGENCY
        self.safety_sm.add_transition(
            SafetyState.ALERT, SafetyState.EMERGENCY,
            guard=lambda ctx: ctx.get('critical_threshold_exceeded', False)
        )
        
        # EMERGENCY -> LOCKDOWN
        self.safety_sm.add_transition(
            SafetyState.EMERGENCY, SafetyState.LOCKDOWN,
            guard=lambda ctx: ctx.get('system_at_risk', False)
        )
        
        # 降级转换
        self.safety_sm.add_transition(
            SafetyState.LOCKDOWN, SafetyState.EMERGENCY,
            guard=lambda ctx: ctx.get('risk_mitigated', False)
        )
        
        self.safety_sm.add_transition(
            SafetyState.EMERGENCY, SafetyState.ALERT,
            guard=lambda ctx: ctx.get('situation_improving', False)
        )
        
        self.safety_sm.add_transition(
            SafetyState.ALERT, SafetyState.WATCH,
            guard=lambda ctx: ctx.get('anomaly_resolved', False)
        )
        
        self.safety_sm.add_transition(
            SafetyState.WATCH, SafetyState.NORMAL,
            guard=lambda ctx: ctx.get('system_stable', False)
        )
        
    def _setup_evolution_transitions(self):
        """配置进化状态转换"""
        # STABLE -> EXPLORING
        self.evolution_sm.add_transition(
            EvolutionState.STABLE, EvolutionState.EXPLORING,
            guard=lambda ctx: ctx.get('exploration_triggered', False)
        )
        
        # EXPLORING -> MICRO_ADJUST
        self.evolution_sm.add_transition(
            EvolutionState.EXPLORING, EvolutionState.MICRO_ADJUST,
            guard=lambda ctx: ctx.get('small_error_detected', False)
        )
        
        # EXPLORING -> REBUILDING
        self.evolution_sm.add_transition(
            EvolutionState.EXPLORING, EvolutionState.REBUILDING,
            guard=lambda ctx: ctx.get('structural_change_needed', False)
        )
        
        # MICRO_ADJUST -> STABLE
        self.evolution_sm.add_transition(
            EvolutionState.MICRO_ADJUST, EvolutionState.STABLE,
            guard=lambda ctx: ctx.get('adjustment_complete', False)
        )
        
        # REBUILDING -> VALIDATING
        self.evolution_sm.add_transition(
            EvolutionState.REBUILDING, EvolutionState.VALIDATING,
            guard=lambda ctx: ctx.get('rebuild_complete', False)
        )
        
        # VALIDATING -> STABLE
        self.evolution_sm.add_transition(
            EvolutionState.VALIDATING, EvolutionState.STABLE,
            guard=lambda ctx: ctx.get('validation_passed', False)
        )
        
        # VALIDATING -> ROLLING_BACK
        self.evolution_sm.add_transition(
            EvolutionState.VALIDATING, EvolutionState.ROLLING_BACK,
            guard=lambda ctx: ctx.get('validation_failed', False)
        )
        
        # ROLLING_BACK -> STABLE
        self.evolution_sm.add_transition(
            EvolutionState.ROLLING_BACK, EvolutionState.STABLE,
            guard=lambda ctx: ctx.get('rollback_complete', False)
        )
        
    # 状态动作实现
    async def _on_start_initializing(self, context):
        """开始初始化"""
        self.agent.logger.info("系统开始初始化")
        
    async def _on_init_complete(self, context):
        """初始化完成"""
        self.agent.logger.info("系统初始化完成")
        
    async def _on_start_running(self, context):
        """开始运行"""
        self.agent.logger.info("系统开始运行")
        
    async def _on_pause(self, context):
        """暂停"""
        self.agent.logger.info("系统暂停")
        
    async def _on_resume(self, context):
        """恢复"""
        self.agent.logger.info("系统恢复")
        
    async def _on_shutdown(self, context):
        """开始关闭"""
        self.agent.logger.info("系统开始关闭")
        
    async def _on_shutdown_complete(self, context):
        """关闭完成"""
        self.agent.logger.info("系统已关闭")
        
    async def _on_fatal_error(self, context):
        """致命错误"""
        self.agent.logger.error(f"系统致命错误: {context.get('error')}")
        
    async def _on_start_review(self, context):
        """开始复盘"""
        self.agent.logger.info("开始离线复盘")
        
    async def _on_review_complete(self, context):
        """复盘完成"""
        self.agent.logger.info("离线复盘完成")
```

## 34.2 生命周期管理

### 34.2.1 Agent生命周期

```python
class AgentLifecycle:
    """
    Agent生命周期管理器
    
    管理Agent从创建到销毁的完整生命周期
    """
    
    def __init__(self, agent):
        self.agent = agent
        self.state_machine = SystemStateMachine(agent)
        self.lifecycle_hooks = {
            'pre_init': [],
            'post_init': [],
            'pre_run': [],
            'post_run': [],
            'pre_pause': [],
            'post_pause': [],
            'pre_resume': [],
            'post_resume': [],
            'pre_shutdown': [],
            'post_shutdown': []
        }
        
    def register_hook(self, stage: str, hook: Callable):
        """注册生命周期钩子"""
        if stage in self.lifecycle_hooks:
            self.lifecycle_hooks[stage].append(hook)
            
    async def execute_hooks(self, stage: str, context: Dict = None):
        """执行生命周期钩子"""
        for hook in self.lifecycle_hooks.get(stage, []):
            if asyncio.iscoroutinefunction(hook):
                await hook(context)
            else:
                hook(context)
                
    async def initialize(self) -> bool:
        """
        初始化生命周期
        
        流程：
        1. 执行pre_init钩子
        2. 状态转换：OFFLINE -> INITIALIZING
        3. 初始化所有模块
        4. 状态转换：INITIALIZING -> READY
        5. 执行post_init钩子
        """
        try:
            await self.execute_hooks('pre_init')
            
            await self.state_machine.system_sm.transition(
                SystemState.INITIALIZING,
                {'start_command': True}
            )
            
            # 初始化模块
            await self.agent.perception.initialize(self.agent.config)
            await self.agent.drive_engine.initialize(self.agent.config)
            await self.agent.task_generator.initialize(self.agent.config)
            await self.agent.decision_maker.initialize(self.agent.config)
            await self.agent.predictor.initialize(self.agent.config)
            await self.agent.memory.initialize(self.agent.config)
            await self.agent.safety_guard.initialize(self.agent.config)
            
            await self.state_machine.system_sm.transition(
                SystemState.READY,
                {'init_complete': True}
            )
            
            await self.execute_hooks('post_init')
            return True
            
        except Exception as e:
            self.agent.logger.error(f"初始化失败: {e}")
            await self.state_machine.system_sm.transition(
                SystemState.SHUTTING_DOWN,
                {'fatal_error': True, 'error': str(e)}
            )
            return False
            
    async def start(self) -> bool:
        """
        启动生命周期
        
        流程：
        1. 执行pre_run钩子
        2. 状态转换：READY -> RUNNING
        3. 启动主循环
        4. 执行post_run钩子
        """
        try:
            await self.execute_hooks('pre_run')
            
            await self.state_machine.system_sm.transition(
                SystemState.RUNNING,
                {'run_command': True}
            )
            
            # 启动主循环
            self.agent.running = True
            while self.agent.running:
                await self._run_cycle()
                
            await self.execute_hooks('post_run')
            return True
            
        except Exception as e:
            self.agent.logger.error(f"运行错误: {e}")
            return False
            
    async def _run_cycle(self):
        """执行单轮循环"""
        # 检查安全状态
        if self.state_machine.safety_sm.current_state == SafetyState.LOCKDOWN:
            await asyncio.sleep(5)
            return
            
        # 执行主循环步骤
        await self.state_machine.runtime_sm.transition(
            RuntimeState.PERCEIVING,
            {'next_state': RuntimeState.PERCEIVING}
        )
        
        perception = await self.agent.perception.perceive()
        
        await self.state_machine.runtime_sm.transition(
            RuntimeState.COMPUTING_DRIVES,
            {'next_state': RuntimeState.COMPUTING_DRIVES}
        )
        
        drives = self.agent.drive_engine.compute(perception)
        
        # 检查是否需要进入复盘
        if self.agent.offline_reviewer.should_review():
            await self.state_machine.runtime_sm.transition(
                RuntimeState.REVIEWING,
                {'review_triggered': True}
            )
            await self.agent.offline_reviewer.review()
            await self.state_machine.runtime_sm.transition(
                RuntimeState.IDLE,
                {'review_complete': True}
            )
            return
            
        await self.state_machine.runtime_sm.transition(
            RuntimeState.GENERATING_TASKS,
            {'next_state': RuntimeState.GENERATING_TASKS}
        )
        
        tasks = self.agent.task_generator.generate(drives, perception)
        
        await self.state_machine.runtime_sm.transition(
            RuntimeState.DECIDING,
            {'next_state': RuntimeState.DECIDING}
        )
        
        selected_task = self.agent.decision_maker.select(tasks, drives)
        
        if selected_task:
            await self.state_machine.runtime_sm.transition(
                RuntimeState.EXECUTING,
                {'next_state': RuntimeState.EXECUTING}
            )
            
            await self.agent.execute_task(selected_task)
            
        await self.state_machine.runtime_sm.transition(
            RuntimeState.PREDICTING,
            {'next_state': RuntimeState.PREDICTING}
        )
        
        prediction = await self.agent.predictor.predict(perception)
        
        await self.state_machine.runtime_sm.transition(
            RuntimeState.LEARNING,
            {'next_state': RuntimeState.LEARNING}
        )
        
        await self.agent.predictor.update(perception, prediction)
        
        await self.state_machine.runtime_sm.transition(
            RuntimeState.IDLE,
            {'cycle_complete': True}
        )
        
    async def pause(self):
        """暂停生命周期"""
        await self.execute_hooks('pre_pause')
        await self.state_machine.system_sm.transition(
            SystemState.PAUSED,
            {'pause_command': True}
        )
        self.agent.running = False
        await self.execute_hooks('post_pause')
        
    async def resume(self):
        """恢复生命周期"""
        await self.execute_hooks('pre_resume')
        await self.state_machine.system_sm.transition(
            SystemState.RUNNING,
            {'resume_command': True}
        )
        self.agent.running = True
        await self.execute_hooks('post_resume')
        
    async def shutdown(self):
        """
        关闭生命周期
        
        流程：
        1. 执行pre_shutdown钩子
        2. 状态转换：RUNNING -> SHUTTING_DOWN
        3. 保存状态
        4. 释放资源
        5. 状态转换：SHUTTING_DOWN -> SHUTDOWN
        6. 执行post_shutdown钩子
        """
        await self.execute_hooks('pre_shutdown')
        
        await self.state_machine.system_sm.transition(
            SystemState.SHUTTING_DOWN,
            {'shutdown_command': True}
        )
        
        self.agent.running = False
        
        # 保存状态
        await self.agent.save_state()
        
        # 释放资源
        await self.agent.perception.shutdown()
        await self.agent.drive_engine.shutdown()
        await self.agent.task_generator.shutdown()
        await self.agent.decision_maker.shutdown()
        await self.agent.predictor.shutdown()
        await self.agent.memory.shutdown()
        await self.agent.safety_guard.shutdown()
        
        await self.state_machine.system_sm.transition(
            SystemState.SHUTDOWN,
            {'cleanup_complete': True}
        )
        
        await self.execute_hooks('post_shutdown')
```

## 34.3 本章小结

本章详细介绍了自驱永续进化Agent系统的状态机与生命周期管理：

1. **状态机设计**：四层状态机（系统级、运行级、安全级、进化级）
2. **状态转换**：守卫条件、进入/退出动作、转换动作
3. **生命周期管理**：初始化、运行、暂停、恢复、关闭的完整流程
4. **生命周期钩子**：支持自定义扩展点

这些设计确保了系统在各种条件下的可控性和可预测性。
