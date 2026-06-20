"""
HTTP服务部署（阶段6：部署与对外API）

第一性原理：神经系统对外暴露两个通道——
  - 感觉输入通道（REST GET）：外部观察者查询Agent内部状态
  - 运动输出通道（REST POST）：外部触发Agent执行动作
  - 广播通道（SSE）：Agent主动向所有观察者推送状态变化

设计原则：
  1. 零外部依赖：仅用Python标准库（http.server + threading + queue）
  2. 向后兼容：保留原有 /health /status /metrics /step /stop 端点
  3. SSE推送：Server-Sent Events 实时推送事件（比WebSocket简单，单向足够）
  4. 安全：所有触发动作的端点尊重 config.execution_dry_run（默认True）
  5. 可观测：Dashboard 内嵌HTML，无需额外静态文件

REST API 端点：
  GET  /health      健康检查
  GET  /status      Agent完整状态
  GET  /metrics     Prometheus格式指标
  GET  /tasks       任务列表
  GET  /strategy    策略库统计
  GET  /security    安全审计日志
  GET  /decision    智能决策建议
  GET  /diagnose    诊断当前系统状态
  POST /step        手动执行一步
  POST /stop        停止Agent
  POST /start       启动Agent
  POST /heal        触发自愈循环
  POST /validate    验证代码修改
  GET  /events      SSE事件流（订阅推送）
  GET  /            Web Dashboard
"""

from __future__ import annotations

import json
import queue
import threading
import time
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional

from agent import SelfEvolvingAgent
from core.config import AgentConfig


# ============================================================================
# 事件广播器（SSE）
# ============================================================================

class EventBroadcaster:
    """
    事件广播器

    第一性原理：类似神经系统的"广播神经元"——一个信号源，
    多个观察者（订阅者）各自接收完整信号副本。

    实现：每个订阅者拥有独立的 queue.Queue，广播时向所有队列写入副本。
    订阅者通过 SSE 长连接读取自己的队列。
    """

    def __init__(self, max_queue_size: int = 256):
        self._subscribers: List[queue.Queue] = []
        self._lock = threading.Lock()
        self._max_queue_size = max_queue_size
        self._event_count = 0

    def subscribe(self) -> queue.Queue:
        """订阅事件流，返回专属队列"""
        q: queue.Queue = queue.Queue(maxsize=self._max_queue_size)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        """取消订阅"""
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        """向所有订阅者广播事件"""
        self._event_count += 1
        event = {
            "id": self._event_count,
            "type": event_type,
            "timestamp": time.time(),
            "data": data,
        }
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                # 队列满，丢弃最旧的事件（保护系统不被慢消费者拖垮）
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "subscriber_count": len(self._subscribers),
                "total_events_broadcast": self._event_count,
            }


# ============================================================================
# Dashboard HTML（内嵌，无需额外文件）
# ============================================================================

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Self-Evolving Agent Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f1419; color: #c9d1d9; }
  .header { background: #161b22; padding: 16px 24px; border-bottom: 1px solid #30363d; display: flex; justify-content: space-between; align-items: center; }
  .header h1 { font-size: 18px; color: #58a6ff; }
  .header .status { font-size: 13px; padding: 4px 12px; border-radius: 12px; }
  .status-running { background: #1a4731; color: #3fb950; }
  .status-stopped { background: #4a1f1f; color: #f85149; }
  .container { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px; }
  .panel { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
  .panel h2 { font-size: 14px; color: #8b949e; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
  .metric-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #21262d; font-size: 13px; }
  .metric-row:last-child { border-bottom: none; }
  .metric-label { color: #8b949e; }
  .metric-value { color: #c9d1d9; font-family: 'SF Mono', monospace; }
  .metric-value.good { color: #3fb950; }
  .metric-value.warn { color: #d29922; }
  .metric-value.bad { color: #f85149; }
  .events { max-height: 320px; overflow-y: auto; font-family: 'SF Mono', monospace; font-size: 12px; }
  .event { padding: 4px 8px; border-bottom: 1px solid #21262d; }
  .event-type { color: #58a6ff; }
  .event-time { color: #8b949e; }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .btn { padding: 8px 16px; background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; cursor: pointer; font-size: 13px; }
  .btn:hover { background: #30363d; }
  .btn-primary { background: #1f6feb; border-color: #1f6feb; color: #fff; }
  .btn-danger { background: #da3633; border-color: #da3633; color: #fff; }
  .full { grid-column: 1 / -1; }
  #toast { position: fixed; bottom: 20px; right: 20px; padding: 12px 20px; background: #161b22; border: 1px solid #30363d; border-radius: 8px; display: none; font-size: 13px; }
</style>
</head>
<body>
<div class="header">
  <h1>Self-Evolving Agent</h1>
  <span id="runStatus" class="status status-stopped">stopped</span>
</div>
<div class="container">
  <div class="panel">
    <h2>Agent Status</h2>
    <div id="statusPanel"><div class="metric-row"><span class="metric-label">loading...</span></span></div></div>
  </div>
  <div class="panel">
    <h2>Execution Stats</h2>
    <div id="execPanel"><div class="metric-row"><span class="metric-label">loading...</span></span></div></div>
  </div>
  <div class="panel">
    <h2>Strategy Library</h2>
    <div id="strategyPanel"><div class="metric-row"><span class="metric-label">loading...</span></span></div></div>
  </div>
  <div class="panel">
    <h2>Security</h2>
    <div id="securityPanel"><div class="metric-row"><span class="metric-label">loading...</span></span></div></div>
  </div>
  <div class="panel full">
    <h2>Live Events (SSE)</h2>
    <div id="events" class="events"><div class="event"><span class="event-time">connecting...</span></div></div>
  </div>
  <div class="panel full">
    <h2>Actions</h2>
    <div class="actions">
      <button class="btn btn-primary" onclick="doAction('/step','POST')">Step</button>
      <button class="btn btn-primary" onclick="doAction('/heal','POST')">Heal</button>
      <button class="btn" onclick="doAction('/diagnose','GET')">Diagnose</button>
      <button class="btn" onclick="doAction('/decision','GET')">Decision</button>
      <button class="btn" onclick="doAction('/tasks','GET')">Tasks</button>
      <button class="btn btn-danger" onclick="doAction('/stop','POST')">Stop</button>
      <button class="btn btn-primary" onclick="doAction('/start','POST')">Start</button>
    </div>
  </div>
</div>
<div id="toast"></div>
<script>
function fmt(v){ return v === undefined ? '-' : String(v); }
function cls(v, warn, bad){ if(v >= bad) return 'bad'; if(v >= warn) return 'warn'; return 'good'; }
function refresh(){
  fetch('/status').then(r=>r.json()).then(d=>{
    const s = d.running ? 'running' : 'stopped';
    document.getElementById('runStatus').textContent = s;
    document.getElementById('runStatus').className = 'status status-'+s;
    let html = '';
    html += row('Step Count', d.step_count);
    html += row('Replay Buffer', d.replay_buffer_size);
    html += row('Memory Size', d.memory_size);
    html += row('Pending Tasks', d.pending_tasks);
    html += row('Optimization Count', d.optimization_count);
    html += row('Evolution Snapshots', d.evolution_snapshots);
    document.getElementById('statusPanel').innerHTML = html;
    let eh = '';
    const es = d.execution_stats || {};
    eh += row('Total Routed', es.total_routed);
    eh += row('Total Executed', es.total_executed);
    eh += row('Total Success', es.total_success);
    eh += row('Total Blocked', es.total_blocked);
    eh += row('Last Execution', d.last_execution_count);
    document.getElementById('execPanel').innerHTML = eh;
    let sh = '';
    const ss = d.strategy_stats || {};
    sh += row('Total Records', ss.total_strategies);
    sh += row('Fault Types', Object.keys(ss.by_fault_type||{}).length);
    sh += row('Top Strategies', (ss.top_strategies||[]).length);
    if(ss.top_strategies){
      ss.top_strategies.slice(0,3).forEach(t=>{
        sh += row('  '+t.action, t.avg_reward.toFixed(3)+' (n='+t.attempts+')');
      });
    }
    document.getElementById('strategyPanel').innerHTML = sh;
    if(d.security_stats){
      let sech = '';
      const sec = d.security_stats;
      sech += row('Total Checks', sec.total_checks);
      sech += row('Total Blocked', sec.total_blocked);
      sech += row('Total Executed', sec.total_executed);
      sech += row('Audit Records', sec.audit_records);
      document.getElementById('securityPanel').innerHTML = sech;
    }
  }).catch(e=>console.error(e));
}
function row(label, value){
  return '<div class="metric-row"><span class="metric-label">'+label+'</span><span class="metric-value">'+fmt(value)+'</span></div>';
}
function doAction(path, method){
  fetch(path, {method: method}).then(r=>r.json()).then(d=>{
    showToast(path+': '+(d.status||d.message||'done'));
    refresh();
  }).catch(e=>showToast(path+' failed: '+e));
}
function showToast(msg){
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.display = 'block';
  setTimeout(()=>t.style.display='none', 3000);
}
function connectSSE(){
  const es = new EventSource('/events');
  es.onmessage = function(e){
    const ev = JSON.parse(e.data);
    const div = document.createElement('div');
    div.className = 'event';
    const t = new Date(ev.timestamp*1000).toLocaleTimeString();
    div.innerHTML = '<span class="event-time">['+t+']</span> <span class="event-type">'+ev.type+'</span> '+JSON.stringify(ev.data).slice(0,200);
    const c = document.getElementById('events');
    c.insertBefore(div, c.firstChild);
    while(c.children.length > 50) c.removeChild(c.lastChild);
  };
  es.onerror = function(){ setTimeout(connectSSE, 3000); };
}
refresh();
setInterval(refresh, 3000);
connectSSE();
</script>
</body>
</html>"""


# ============================================================================
# HTTP 请求处理器
# ============================================================================

class AgentHandler(BaseHTTPRequestHandler):
    """HTTP请求处理器（阶段6扩展版）"""

    agent: Optional[SelfEvolvingAgent] = None
    broadcaster: Optional[EventBroadcaster] = None

    def log_message(self, format, *args):
        """静默默认日志（避免污染输出）"""
        pass

    # --- 工具方法 ---

    def _send_json(self, data: Any, status: int = 200):
        """发送JSON响应"""
        body = json.dumps(data, indent=2, default=str, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: int = 200):
        """发送HTML响应"""
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> Dict[str, Any]:
        """读取POST body并解析为JSON（空body返回{}）"""
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        try:
            raw = self.rfile.read(length)
            return json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            return {}

    def _require_agent(self) -> bool:
        """检查Agent是否已初始化，未初始化则返回503并返回False"""
        if self.agent is None:
            self._send_json({"error": "Agent not initialized"}, 503)
            return False
        return True

    def _broadcast(self, event_type: str, data: Dict[str, Any]):
        """广播事件（如果broadcaster可用）"""
        if self.broadcaster is not None:
            self.broadcaster.broadcast(event_type, data)

    # --- GET 路由 ---

    def do_GET(self):
        path = self.path.split("?")[0]  # 去掉query string
        routes = {
            "/": self._handle_dashboard,
            "/dashboard": self._handle_dashboard,
            "/health": self._handle_health,
            "/status": self._handle_status,
            "/metrics": self._handle_metrics,
            "/tasks": self._handle_tasks,
            "/strategy": self._handle_strategy,
            "/security": self._handle_security,
            "/decision": self._handle_decision,
            "/diagnose": self._handle_diagnose,
            "/events": self._handle_sse,
        }
        handler = routes.get(path)
        if handler:
            handler()
        else:
            self._send_json({"error": "Not found", "path": path}, 404)

    # --- POST 路由 ---

    def do_POST(self):
        path = self.path.split("?")[0]
        routes = {
            "/step": self._handle_step,
            "/stop": self._handle_stop,
            "/start": self._handle_start,
            "/heal": self._handle_heal,
            "/validate": self._handle_validate,
        }
        handler = routes.get(path)
        if handler:
            handler()
        else:
            self._send_json({"error": "Not found", "path": path}, 404)

    # ========================================================================
    # GET 端点实现
    # ========================================================================

    def _handle_dashboard(self):
        """Web Dashboard页面"""
        self._send_html(DASHBOARD_HTML)

    def _handle_health(self):
        """健康检查"""
        if self.agent is None:
            self._send_json({"status": "not_initialized"}, 503)
            return
        self._send_json({
            "status": "healthy" if self.agent.running else "stopped",
            "step_count": self.agent.step_count,
            "timestamp": time.time(),
        })

    def _handle_status(self):
        """Agent完整状态（含执行/策略/安全统计）"""
        if not self._require_agent():
            return
        status = self.agent.get_status()
        # 补充安全统计（阶段3）
        if hasattr(self.agent, 'task_router') and hasattr(self.agent.task_router, 'security_guard'):
            status["security_stats"] = self.agent.task_router.security_guard.get_stats()
        # 补充广播统计
        if self.broadcaster is not None:
            status["broadcaster_stats"] = self.broadcaster.get_stats()
        self._send_json(status)

    def _handle_metrics(self):
        """Prometheus格式指标"""
        if not self._require_agent():
            return
        a = self.agent
        lines = [
            f"# TYPE agent_steps_total counter",
            f"agent_steps_total {a.step_count}",
            f"# TYPE agent_running gauge",
            f"agent_running {1 if a.running else 0}",
            f"# TYPE replay_buffer_size gauge",
            f"replay_buffer_size {len(a.replay_buffer)}",
            f"# TYPE optimization_count gauge",
            f"optimization_count {a._optimization_count}",
        ]
        # 执行统计
        if hasattr(a, 'task_router'):
            stats = a.task_router.get_stats()
            for k, v in stats.items():
                if isinstance(v, (int, float)):
                    lines.append(f"# TYPE exec_{k} gauge")
                    lines.append(f"exec_{k} {v}")
        # 策略统计
        if hasattr(a, 'strategy_library'):
            stats = a.strategy_library.get_stats()
            lines.append(f"# TYPE strategy_total_records gauge")
            lines.append(f"strategy_total_records {stats.get('total_strategies', 0)}")
        body = "\n".join(lines) + "\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body.encode())))
        self.end_headers()
        self.wfile.write(body.encode())

    def _handle_tasks(self):
        """任务列表"""
        if not self._require_agent():
            return
        tg = self.agent.task_generator
        pending = tg.get_pending_tasks() if hasattr(tg, 'get_pending_tasks') else []
        tasks_data = []
        for t in pending[:50]:  # 最多返回50个
            tasks_data.append({
                "id": getattr(t, 'id', ''),
                "name": getattr(t, 'name', ''),
                "description": getattr(t, 'description', ''),
                "priority": str(getattr(t, 'priority', '')),
                "status": str(getattr(t, 'status', '')),
                "action": getattr(t, 'action', None),
                "reward": getattr(t, 'reward', None),
            })
        self._send_json({
            "pending_count": len(pending),
            "tasks": tasks_data,
        })

    def _handle_strategy(self):
        """策略库统计"""
        if not self._require_agent():
            return
        if not hasattr(self.agent, 'strategy_library'):
            self._send_json({"error": "strategy_library not available"}, 503)
            return
        self._send_json(self.agent.strategy_library.get_stats())

    def _handle_security(self):
        """安全审计日志"""
        if not self._require_agent():
            return
        if not hasattr(self.agent, 'task_router') or not hasattr(self.agent.task_router, 'security_guard'):
            self._send_json({"error": "security_guard not available"}, 503)
            return
        sg = self.agent.task_router.security_guard
        audit = sg.get_audit_log(limit=50)
        self._send_json({
            "stats": sg.get_stats(),
            "audit_log": [
                {
                    "timestamp": r.timestamp,
                    "command": r.command,
                    "allowed": r.allowed,
                    "risk_level": r.risk_level,
                    "reason": r.reason,
                    "exit_code": r.exit_code,
                    "stderr": r.stderr,
                }
                for r in audit
            ],
        })

    def _handle_decision(self):
        """智能决策建议（基于当前状态）"""
        if not self._require_agent():
            return
        from learning import IntelligentDecisionMaker, MetricsSnapshot
        if self.agent.current_state is None:
            self._send_json({"error": "no current state available, run /step first"}, 409)
            return
        snapshot = MetricsSnapshot.from_state_vector(self.agent.current_state)
        dm = IntelligentDecisionMaker(
            strategy_library=self.agent.strategy_library
        )
        decision = dm.decide(snapshot)
        # 找到被选中的候选（用于提取 source/confidence）
        chosen_candidate = None
        for c in decision.candidates:
            if c.action == decision.chosen_action:
                chosen_candidate = c
                break
        self._send_json({
            "fault_type": self.agent.strategy_library.classify_fault(snapshot),
            "action": decision.chosen_action,
            "source": chosen_candidate.source if chosen_candidate else "default",
            "confidence": chosen_candidate.confidence if chosen_candidate else 0.0,
            "exploration": decision.exploration,
            "reasoning": decision.reason_chain,
            "candidates_count": len(decision.candidates),
        })

    def _handle_diagnose(self):
        """诊断当前系统状态"""
        if not self._require_agent():
            return
        from core.auto_healing import AutoHealingEngine
        if self.agent.current_state is None:
            self._send_json({"error": "no current state available, run /step first"}, 409)
            return
        # 从状态向量提取关键指标
        sv = self.agent.current_state
        metrics = {
            "cpu_percent": float(sv[0]) if len(sv) > 0 else 0.0,
            "memory_percent": float(sv[10]) if len(sv) > 10 else 0.0,
            "disk_percent": float(sv[20]) if len(sv) > 20 else 0.0,
        }
        engine = AutoHealingEngine()
        anomaly = engine.detect_anomaly(metrics)
        diagnosis = engine.diagnose_root_cause(metrics)
        self._send_json({
            "metrics": metrics,
            "anomaly": anomaly,
            "diagnosis": diagnosis,
        })

    def _handle_sse(self):
        """SSE事件流（长连接推送）"""
        if self.broadcaster is None:
            self._send_json({"error": "broadcaster not available"}, 503)
            return
        q = self.broadcaster.subscribe()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            # 发送初始连接事件
            self._sse_write({"type": "connected", "data": {"message": "SSE connected"}})
            while True:
                try:
                    event = q.get(timeout=15)
                    self._sse_write(event)
                except queue.Empty:
                    # 发送心跳保活
                    self._sse_write({"type": "heartbeat", "data": {"ts": time.time()}})
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.broadcaster.unsubscribe(q)

    def _sse_write(self, event: Dict[str, Any]):
        """写入一条SSE事件"""
        try:
            data = json.dumps(event, default=str, ensure_ascii=False)
            self.wfile.write(f"data: {data}\n\n".encode())
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            raise

    # ========================================================================
    # POST 端点实现
    # ========================================================================

    def _handle_step(self):
        """手动执行一步"""
        if not self._require_agent():
            return
        result = self.agent.step()
        self._broadcast("step", {"step_count": self.agent.step_count, "result": result})
        self._send_json(result)

    def _handle_stop(self):
        """停止Agent"""
        if not self._require_agent():
            return
        self.agent.stop()
        self._broadcast("lifecycle", {"event": "stopped"})
        self._send_json({"status": "stopped", "step_count": self.agent.step_count})

    def _handle_start(self):
        """启动Agent（在后台线程中运行主循环）"""
        if not self._require_agent():
            return
        if self.agent.running:
            self._send_json({"status": "already_running"})
            return
        # 在后台线程启动主循环（避免阻塞HTTP服务）
        def _run():
            self.agent.start()
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        self._broadcast("lifecycle", {"event": "started"})
        self._send_json({"status": "starting", "message": "Agent主循环已在后台启动"})

    def _handle_heal(self):
        """触发自愈循环"""
        if not self._require_agent():
            return
        from core.auto_healing import AutoHealingEngine
        if self.agent.current_state is None:
            self._send_json({"error": "no current state available, run /step first"}, 409)
            return
        sv = self.agent.current_state
        metrics = {
            "cpu_percent": float(sv[0]) if len(sv) > 0 else 0.0,
            "memory_percent": float(sv[10]) if len(sv) > 10 else 0.0,
            "disk_percent": float(sv[20]) if len(sv) > 20 else 0.0,
        }
        engine = AutoHealingEngine()
        result = engine.run_healing_cycle(metrics)
        self._broadcast("heal", {"metrics": metrics, "result": result})
        self._send_json(result)

    def _handle_validate(self):
        """验证代码修改

        请求body:
            {
                "file_path": "/path/to/file.py",
                "patched_source": "...",
                "test_path": "optional/test_path.py"
            }
        """
        if not self._require_agent():
            return
        from pathlib import Path
        from core.test_validator import TestValidator
        body = self._read_body()
        file_path_str = body.get("file_path")
        patched_source = body.get("patched_source")
        test_path = body.get("test_path")
        if not file_path_str or not patched_source:
            self._send_json({"error": "需要提供 file_path 和 patched_source"}, 400)
            return
        file_path = Path(file_path_str)
        validator = TestValidator()
        report = validator.validate_change(
            file_path=file_path,
            patched_source=patched_source,
            test_path=test_path,
        )
        self._broadcast("validation", {
            "file": file_path_str,
            "verdict": report.verdict,
        })
        self._send_json({
            "verdict": report.verdict,
            "rollback_reason": report.rollback_reason,
            "baseline_tests": {
                "passed": report.baseline_tests.passed_count,
                "failed": report.baseline_tests.failed_count,
            } if report.baseline_tests else None,
            "post_change_tests": {
                "passed": report.post_change_tests.passed_count,
                "failed": report.post_change_tests.failed_count,
            } if report.post_change_tests else None,
            "baseline_benchmark_ms": report.baseline_benchmark.avg_time_ms if report.baseline_benchmark else None,
            "post_change_benchmark_ms": report.post_change_benchmark.avg_time_ms if report.post_change_benchmark else None,
        })


# ============================================================================
# 服务器封装
# ============================================================================

class AgentServer:
    """
    Agent HTTP服务器（阶段6增强版）

    使用示例：
        server = AgentServer(agent, port=8080)
        server.start()
        # ...
        server.stop()

    事件广播：
        server.broadcaster.broadcast("custom_event", {"key": "value"})
    """

    def __init__(self, agent: SelfEvolvingAgent, port: int = 8080):
        self.agent = agent
        self.port = port
        self.broadcaster = EventBroadcaster()
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """启动服务器（非阻塞）"""
        AgentHandler.agent = self.agent
        AgentHandler.broadcaster = self.broadcaster
        self._server = ThreadingHTTPServer(("0.0.0.0", self.port), AgentHandler)
        # 如果port=0，获取系统分配的实际端口
        if self.port == 0:
            self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        print(f"Agent HTTP server started on port {self.port}")
        print(f"  Dashboard: http://localhost:{self.port}/")
        print(f"  API docs:  http://localhost:{self.port}/status")
        print(f"  SSE stream: http://localhost:{self.port}/events")

    @property
    def actual_port(self) -> int:
        """获取实际绑定的端口"""
        return self.port

    def stop(self):
        """停止服务器"""
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        print("Agent HTTP server stopped")

    def broadcast(self, event_type: str, data: Dict[str, Any]):
        """广播事件给所有SSE订阅者"""
        self.broadcaster.broadcast(event_type, data)


def main():
    """主入口"""
    import sys

    # 解析参数
    port = 8080
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    # 创建配置
    config = AgentConfig()
    config.main_loop_interval_ms = 5000  # 生产环境5秒一次

    # 创建Agent
    agent = SelfEvolvingAgent(config)

    # 启动HTTP服务
    server = AgentServer(agent, port=port)
    server.start()

    # 启动Agent主循环
    try:
        agent.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        agent.stop()
        server.stop()


if __name__ == "__main__":
    main()
