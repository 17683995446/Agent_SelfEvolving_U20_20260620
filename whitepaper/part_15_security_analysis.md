# 安全分析与风险管控

## 1. 安全威胁模型

### 1.1 威胁分类

```
┌─────────────────────────────────────────────────────────────┐
│                     安全威胁模型                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  外部威胁                                                    │
│  ├── 恶意代码注入                                            │
│  ├── 未授权访问                                              │
│  ├── 网络攻击（如适用）                                       │
│  └── 社会工程学攻击                                          │
│                                                             │
│  内部威胁                                                    │
│  ├── Agent自身失控                                           │
│  ├── 模型退化导致错误决策                                     │
│  ├── 探索行为导致资源耗尽                                     │
│  └── 认知偏差导致系统性错误                                   │
│                                                             │
│  环境威胁                                                    │
│  ├── 系统资源耗尽                                            │
│  ├── 存储空间溢出                                            │
│  ├── 日志文件膨胀                                            │
│  └── 外部系统变更导致不适应                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 风险评估矩阵

| 威胁 | 可能性 | 影响 | 风险等级 | 缓解措施 |
|-----|-------|------|---------|---------|
| Agent失控 | 低 | 高 | 中 | 资源约束、行为约束 |
| 模型退化 | 中 | 中 | 中 | 自动回滚、效果验证 |
| 资源耗尽 | 低 | 高 | 中 | 资源上限、动态降频 |
| 探索过度 | 中 | 低 | 低 | 探索止损、比例限制 |
| 数据泄露 | 低 | 高 | 中 | 本地存储、无联网 |

## 2. 多层安全防护体系

### 2.1 第一层：资源沙箱

```python
class ResourceSandbox:
    """资源沙箱：限制Agent的资源使用"""
    
    def __init__(self, config):
        self.cpu_limit = config.max_cpu_percent
        self.memory_limit = config.max_memory_percent
        self.disk_limit = config.max_disk_gb
        
        # 设置系统级资源限制
        self._setup_system_limits()
    
    def _setup_system_limits(self):
        """设置操作系统级资源限制"""
        import resource
        
        # CPU时间限制（软限制）
        soft_cpu = int(self.cpu_limit * 3600)
        resource.setrlimit(resource.RLIMIT_CPU, (soft_cpu, soft_cpu + 60))
        
        # 内存限制
        mem_bytes = int(self.memory_limit * 1024 * 1024 * 1024)
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        
        # 文件大小限制
        disk_bytes = int(self.disk_limit * 1024 * 1024 * 1024)
        resource.setrlimit(resource.RLIMIT_FSIZE, (disk_bytes, disk_bytes))
    
    def check_and_enforce(self):
        """检查并强制执行资源限制"""
        current_cpu = get_agent_cpu_usage()
        current_mem = get_agent_memory_usage()
        
        if current_cpu > self.cpu_limit:
            self._reduce_cpu_usage()
        
        if current_mem > self.memory_limit:
            self._reduce_memory_usage()
    
    def _reduce_cpu_usage(self):
        """降低CPU使用"""
        # 降低采样频率
        PerceptionModule.reduce_sampling_frequency()
        
        # 跳过非关键计算
        Predictor.skip_non_critical_predictions()
        
        # 延迟复盘任务
        OfflineReview.delay_review()
    
    def _reduce_memory_usage(self):
        """降低内存使用"""
        # 清理缓存
        MemorySystem.clear_caches()
        
        # 压缩模型
        Predictor.compress_models()
        
        # 释放历史数据
        MemorySystem.purge_old_data()
```

### 2.2 第二层：行为约束

```python
class BehaviorConstraint:
    """行为约束：限制Agent的行为范围"""
    
    FORBIDDEN_ACTIONS = [
        'modify_system_files',
        'delete_user_data',
        'modify_network_config',
        'execute_shell_commands',
        'access_sensitive_paths',
        'modify_self_code',
        'create_network_connections',
    ]
    
    FORBIDDEN_PATHS = [
        '/etc/passwd',
        '/etc/shadow',
        '/etc/sudoers',
        '/proc/sys',
        '/sys',
        '/dev',
        '/boot',
        '/bin',
        '/sbin',
    ]
    
    @classmethod
    def validate_action(cls, action):
        """验证行为是否允许"""
        if action.type in cls.FORBIDDEN_ACTIONS:
            raise ForbiddenActionError(f"Action {action.type} is forbidden")
        
        if hasattr(action, 'target_path'):
            if any(action.target_path.startswith(p) for p in cls.FORBIDDEN_PATHS):
                raise ForbiddenPathError(f"Path {action.target_path} is forbidden")
        
        return True
    
    @classmethod
    def validate_task(cls, task):
        """验证任务是否安全"""
        # 检查任务类型
        if task.task_type in ['system_modify', 'kernel_tweak']:
            return False
        
        # 检查资源需求
        if task.required_cpu > 0.5 or task.required_memory > 1000:
            # 高资源任务需要额外验证
            return cls._validate_high_resource_task(task)
        
        return True
    
    @classmethod
    def _validate_high_resource_task(cls, task):
        """验证高资源任务"""
        # 检查当前系统状态
        if get_system_cpu() > 80 or get_system_memory() > 90:
            return False
        
        # 检查任务历史
        if task.execution_count > 10 and task.success_rate < 0.5:
            return False
        
        return True
```

### 2.3 第三层：进化约束

```python
class EvolutionConstraint:
    """进化约束：防止进化失控"""
    
    MAX_EXPLORATION_RATE = 0.5
    MIN_EXPLOITATION_RATE = 0.5
    MAX_RECONSTRUCTION_FREQUENCY = 1  # 每天最多1次
    MAX_MODEL_COMPLEXITY = 1000000    # 最大参数数量
    
    @classmethod
    def validate_exploration_rate(cls, rate):
        """验证探索率"""
        return min(rate, cls.MAX_EXPLORATION_RATE)
    
    @classmethod
    def validate_reconstruction(cls, last_reconstruction_time):
        """验证重构频率"""
        hours_since_last = (datetime.now() - last_reconstruction_time).total_seconds() / 3600
        return hours_since_last >= 24 / cls.MAX_RECONSTRUCTION_FREQUENCY
    
    @classmethod
    def validate_model_complexity(cls, model):
        """验证模型复杂度"""
        param_count = sum(p.numel() for p in model.parameters())
        return param_count <= cls.MAX_MODEL_COMPLEXITY
    
    @classmethod
    def validate_exploration_result(cls, exploration_result):
        """验证探索结果"""
        # 连续失败检查
        if exploration_result.consecutive_failures >= 5:
            return False
        
        # 资源消耗检查
        if exploration_result.resource_consumed > exploration_result.value_generated * 2:
            return False
        
        return True
```

## 3. 异常行为检测

### 3.1 自身行为监控

```python
class SelfBehaviorMonitor:
    """监控Agent自身行为，检测异常"""
    
    def __init__(self):
        self.behavior_history = deque(maxlen=1000)
        self.baseline_behavior = None
    
    def record_behavior(self, behavior):
        """记录行为"""
        self.behavior_history.append({
            'timestamp': datetime.now(),
            'action_type': behavior.type,
            'resource_cost': behavior.resource_cost,
            'target': behavior.target,
            'result': behavior.result
        })
    
    def detect_anomaly(self):
        """检测异常行为"""
        anomalies = []
        
        # 检测异常行为模式
        if self._detect_repetitive_behavior():
            anomalies.append("Repetitive behavior detected")
        
        if self._detect_resource_spike():
            anomalies.append("Resource usage spike detected")
        
        if self._detect_circular_behavior():
            anomalies.append("Circular behavior detected")
        
        if self._detect_aggressive_exploration():
            anomalies.append("Aggressive exploration detected")
        
        return anomalies
    
    def _detect_repetitive_behavior(self):
        """检测重复行为"""
        recent = list(self.behavior_history)[-50:]
        if len(recent) < 50:
            return False
        
        # 检查最近50个行为中是否有超过30个相同类型
        type_counts = Counter(b['action_type'] for b in recent)
        most_common = type_counts.most_common(1)[0]
        
        return most_common[1] > 30
    
    def _detect_resource_spike(self):
        """检测资源使用突增"""
        recent = list(self.behavior_history)[-20:]
        if len(recent) < 20:
            return False
        
        avg_cost = mean(b['resource_cost'] for b in recent[:-5])
        recent_cost = mean(b['resource_cost'] for b in recent[-5:])
        
        return recent_cost > avg_cost * 3
    
    def _detect_circular_behavior(self):
        """检测循环行为"""
        # 检查是否在不同任务间循环切换
        recent = list(self.behavior_history)[-30:]
        if len(recent) < 30:
            return False
        
        # 检测A→B→A→B模式
        for i in range(len(recent) - 3):
            if (recent[i]['action_type'] == recent[i+2]['action_type'] and
                recent[i+1]['action_type'] == recent[i+3]['action_type'] and
                recent[i]['action_type'] != recent[i+1]['action_type']):
                return True
        
        return False
    
    def _detect_aggressive_exploration(self):
        """检测过度探索"""
        recent = list(self.behavior_history)[-100:]
        if len(recent) < 100:
            return False
        
        exploration_count = sum(1 for b in recent if b.get('is_exploration', False))
        exploration_rate = exploration_count / len(recent)
        
        return exploration_rate > 0.5
```

### 3.2 自动恢复机制

```python
class AutoRecovery:
    """自动恢复机制"""
    
    def __init__(self, agent):
        self.agent = agent
        self.recovery_strategies = {
            'resource_exhaustion': self._recover_resource_exhaustion,
            'model_degradation': self._recover_model_degradation,
            'exploration_loop': self._recover_exploration_loop,
            'task_overflow': self._recover_task_overflow,
        }
    
    def trigger_recovery(self, issue_type):
        """触发恢复"""
        if issue_type in self.recovery_strategies:
            return self.recovery_strategies[issue_type]()
        return False
    
    def _recover_resource_exhaustion(self):
        """恢复资源耗尽"""
        # 1. 暂停非关键任务
        self.agent.pause_non_critical_tasks()
        
        # 2. 清理内存
        self.agent.memory.emergency_cleanup()
        
        # 3. 降低采样频率
        self.agent.perception.reduce_frequency()
        
        # 4. 压缩模型
        self.agent.predictor.emergency_compress()
        
        return True
    
    def _recover_model_degradation(self):
        """恢复模型退化"""
        # 1. 回滚到上一个稳定快照
        last_stable = self.agent.memory.get_last_stable_snapshot()
        if last_stable:
            self.agent.rollback_to_snapshot(last_stable)
            return True
        
        # 2. 如果没有快照，重置到基线模型
        self.agent.predictor.reset_to_baseline()
        return True
    
    def _recover_exploration_loop(self):
        """恢复探索循环"""
        # 1. 强制切换到利用模式
        self.agent.decision_engine.force_exploitation(duration=300)
        
        # 2. 冻结探索任务
        self.agent.task_generator.freeze_exploration_tasks()
        
        # 3. 重置探索率
        self.agent.decision_engine.reset_exploration_rate()
        
        return True
    
    def _recover_task_overflow(self):
        """恢复任务溢出"""
        # 1. 清空任务池
        self.agent.task_generator.clear_pool()
        
        # 2. 仅保留高优先级任务
        self.agent.task_generator.retain_high_priority_only()
        
        # 3. 降低任务生成频率
        self.agent.task_generator.reduce_generation_rate()
        
        return True
```

## 4. 数据安全

### 4.1 本地存储安全

```python
class SecureStorage:
    """安全存储"""
    
    def __init__(self, storage_path):
        self.storage_path = storage_path
        self.encryption_key = self._generate_key()
    
    def _generate_key(self):
        """生成加密密钥"""
        # 使用系统唯一标识生成密钥
        system_id = get_system_fingerprint()
        return hashlib.sha256(system_id.encode()).digest()
    
    def encrypt_data(self, data):
        """加密数据"""
        from cryptography.fernet import Fernet
        f = Fernet(base64.urlsafe_b64encode(self.encryption_key))
        return f.encrypt(data.encode())
    
    def decrypt_data(self, encrypted_data):
        """解密数据"""
        from cryptography.fernet import Fernet
        f = Fernet(base64.urlsafe_b64encode(self.encryption_key))
        return f.decrypt(encrypted_data).decode()
    
    def secure_write(self, filename, data):
        """安全写入"""
        encrypted = self.encrypt_data(json.dumps(data))
        filepath = os.path.join(self.storage_path, filename)
        
        # 设置文件权限
        with open(filepath, 'wb') as f:
            f.write(encrypted)
        
        os.chmod(filepath, 0o600)  # 仅所有者可读写
    
    def secure_read(self, filename):
        """安全读取"""
        filepath = os.path.join(self.storage_path, filename)
        
        with open(filepath, 'rb') as f:
            encrypted = f.read()
        
        return json.loads(self.decrypt_data(encrypted))
```

### 4.2 隐私保护

```python
class PrivacyProtection:
    """隐私保护"""
    
    SENSITIVE_PATTERNS = [
        r'password[=:]\s*\S+',
        r'token[=:]\s*\S+',
        r'secret[=:]\s*\S+',
        r'api[_-]?key[=:]\s*\S+',
        r'private[_-]?key[=:]\s*\S+',
    ]
    
    @classmethod
    def sanitize_log(cls, log_content):
        """清理日志中的敏感信息"""
        sanitized = log_content
        
        for pattern in cls.SENSITIVE_PATTERNS:
            sanitized = re.sub(pattern, '***REDACTED***', sanitized, flags=re.IGNORECASE)
        
        return sanitized
    
    @classmethod
    def sanitize_state_vector(cls, state_vector):
        """清理状态向量中的敏感信息"""
        # 移除可能包含敏感信息的高维特征
        safe_vector = state_vector.copy()
        
        # 不记录具体的进程名称（可能包含敏感应用）
        if 'process_names' in safe_vector:
            del safe_vector['process_names']
        
        # 不记录具体的文件路径
        if 'file_paths' in safe_vector:
            del safe_vector['file_paths']
        
        return safe_vector
```

## 5. 审计与合规

### 5.1 完整审计日志

```python
class AuditLogger:
    """审计日志"""
    
    def __init__(self):
        self.logger = logging.getLogger('audit')
        self.logger.setLevel(logging.INFO)
        
        # 审计日志文件
        handler = logging.handlers.RotatingFileHandler(
            'logs/audit.log',
            maxBytes=10*1024*1024,
            backupCount=50
        )
        handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
    
    def log_action(self, action, result, context):
        """记录行为审计"""
        audit_record = {
            'timestamp': datetime.now().isoformat(),
            'action_type': action.type,
            'action_id': action.id,
            'result': result,
            'resource_cost': context.resource_cost,
            'system_state': context.system_state_hash,
        }
        
        self.logger.info(json.dumps(audit_record))
    
    def log_decision(self, decision, alternatives):
        """记录决策审计"""
        audit_record = {
            'timestamp': datetime.now().isoformat(),
            'decision_type': 'task_selection',
            'selected_task': decision.selected_task.id,
            'selection_mode': decision.mode,
            'exploration_rate': decision.exploration_rate,
            'alternatives': [alt.id for alt in alternatives],
            'scores': {alt.id: alt.score for alt in alternatives},
        }
        
        self.logger.info(json.dumps(audit_record))
    
    def log_evolution(self, evolution_event):
        """记录进化审计"""
        audit_record = {
            'timestamp': datetime.now().isoformat(),
            'event_type': evolution_event.type,
            'before_state': evolution_event.before_state_hash,
            'after_state': evolution_event.after_state_hash,
            'performance_delta': evolution_event.performance_delta,
            'trigger_reason': evolution_event.trigger_reason,
        }
        
        self.logger.info(json.dumps(audit_record))
```

### 5.2 合规检查

```python
class ComplianceChecker:
    """合规检查"""
    
    COMPLIANCE_RULES = [
        'resource_limits_enforced',
        'forbidden_actions_blocked',
        'data_encrypted_at_rest',
        'audit_logs_complete',
        'no_external_network_access',
        'user_data_protected',
    ]
    
    def run_compliance_check(self):
        """运行合规检查"""
        results = {}
        
        for rule in self.COMPLIANCE_RULES:
            check_method = getattr(self, f'_check_{rule}')
            results[rule] = check_method()
        
        return results
    
    def _check_resource_limits_enforced(self):
        """检查资源限制是否生效"""
        cpu_usage = get_agent_cpu_usage()
        mem_usage = get_agent_memory_usage()
        
        return cpu_usage <= 20 and mem_usage <= 20
    
    def _check_forbidden_actions_blocked(self):
        """检查禁止行为是否被阻止"""
        # 检查审计日志中是否有禁止行为记录
        audit_logs = load_recent_audit_logs()
        forbidden_actions = [log for log in audit_logs 
                           if log.get('action_type') in BehaviorConstraint.FORBIDDEN_ACTIONS]
        
        return len(forbidden_actions) == 0
    
    def _check_data_encrypted_at_rest(self):
        """检查数据是否加密存储"""
        storage_files = list_storage_files()
        
        for file in storage_files:
            if not is_encrypted(file):
                return False
        
        return True
    
    def _check_audit_logs_complete(self):
        """检查审计日志是否完整"""
        # 检查最近1小时是否有审计日志
        recent_logs = load_audit_logs(since=datetime.now() - timedelta(hours=1))
        
        return len(recent_logs) > 0
    
    def _check_no_external_network_access(self):
        """检查是否有外部网络访问"""
        # 检查网络连接
        connections = get_agent_network_connections()
        external_connections = [c for c in connections if not c.is_local]
        
        return len(external_connections) == 0
    
    def _check_user_data_protected(self):
        """检查用户数据是否受保护"""
        # 检查是否访问了用户数据目录
        audit_logs = load_recent_audit_logs()
        user_data_access = [log for log in audit_logs 
                          if 'user_data' in log.get('target', '')]
        
        return len(user_data_access) == 0
```

---

安全分析与风险管控部分建立了完整的安全防护体系，从资源沙箱、行为约束到进化约束，从异常检测到自动恢复，确保Agent系统在自主进化的同时始终保持安全可控。
