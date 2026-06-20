"""
阶段6测试：部署与对外API

测试覆盖：
  1. EventBroadcaster：订阅/取消/广播/队列满处理
  2. AgentServer：启动/停止
  3. REST API：所有GET/POST端点
  4. SSE推送：事件流
  5. Dashboard：HTML响应
  6. 向后兼容：原有端点仍可用
  7. 错误处理：404/503

第一性原理验证：
  - 感觉输入通道（GET）能正确反映Agent内部状态
  - 运动输出通道（POST）能正确触发Agent动作
  - 广播通道（SSE）能正确推送事件给多个订阅者
"""

import sys
import os
import time
import json
import queue
import threading
import urllib.request
import urllib.error

# 确保能导入模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deployment.server import EventBroadcaster, AgentServer, AgentHandler, DASHBOARD_HTML
from agent import SelfEvolvingAgent
from core.config import AgentConfig
import numpy as np


# ============================================================================
# 测试框架
# ============================================================================

passed = 0
failed = 0


def assert_true(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {msg}")
    else:
        failed += 1
        print(f"  [FAIL] {msg}")


def assert_eq(actual, expected, msg):
    assert_true(actual == expected, f"{msg} (expected={expected}, actual={actual})")


def assert_in(sub, container, msg):
    assert_true(sub in container, f"{msg} ('{sub}' not in {str(container)[:100]})")


# ============================================================================
# HTTP 客户端工具
# ============================================================================

def http_get(url, timeout=5):
    """发起GET请求，返回 (status_code, body_text)"""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def http_post(url, body=None, timeout=5):
    """发起POST请求，返回 (status_code, body_text)"""
    try:
        data = json.dumps(body).encode() if body else b""
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


# ============================================================================
# 测试用例
# ============================================================================

def test_event_broadcaster_basic():
    """测试1: EventBroadcaster 基本操作"""
    print("\n--- 测试1: EventBroadcaster 基本操作 ---")
    eb = EventBroadcaster()

    # 订阅
    q = eb.subscribe()
    stats = eb.get_stats()
    assert_eq(stats["subscriber_count"], 1, "订阅后 subscriber_count=1")

    # 广播
    eb.broadcast("test_event", {"key": "value"})
    event = q.get(timeout=1)
    assert_eq(event["type"], "test_event", "事件类型正确")
    assert_eq(event["data"]["key"], "value", "事件数据正确")
    assert_true(event["id"] > 0, "事件ID>0")
    assert_true(event["timestamp"] > 0, "事件时间戳>0")

    # 取消订阅
    eb.unsubscribe(q)
    stats = eb.get_stats()
    assert_eq(stats["subscriber_count"], 0, "取消后 subscriber_count=0")


def test_event_broadcaster_multi_subscribers():
    """测试2: 多订阅者广播"""
    print("\n--- 测试2: 多订阅者广播 ---")
    eb = EventBroadcaster()
    q1 = eb.subscribe()
    q2 = eb.subscribe()
    q3 = eb.subscribe()
    assert_eq(eb.get_stats()["subscriber_count"], 3, "3个订阅者")

    eb.broadcast("broadcast", {"msg": "hello"})
    e1 = q1.get(timeout=1)
    e2 = q2.get(timeout=1)
    e3 = q3.get(timeout=1)
    assert_eq(e1["data"]["msg"], "hello", "订阅者1收到")
    assert_eq(e2["data"]["msg"], "hello", "订阅者2收到")
    assert_eq(e3["data"]["msg"], "hello", "订阅者3收到")
    assert_eq(e1["id"], e2["id"], "订阅者1和2收到相同ID事件")
    assert_eq(e2["id"], e3["id"], "订阅者2和3收到相同ID事件")


def test_event_broadcaster_queue_full():
    """测试3: 队列满时丢弃最旧事件"""
    print("\n--- 测试3: 队列满时丢弃最旧事件 ---")
    eb = EventBroadcaster(max_queue_size=3)
    q = eb.subscribe()

    # 发送5个事件（队列容量3）
    for i in range(5):
        eb.broadcast("evt", {"idx": i})

    # 应该能取到3个（idx=2,3,4），最旧的idx=0,1被丢弃
    events = []
    while True:
        try:
            events.append(q.get_nowait())
        except queue.Empty:
            break
    assert_eq(len(events), 3, "队列满后保留3个事件")
    assert_eq(events[0]["data"]["idx"], 2, "最旧的是idx=2")
    assert_eq(events[2]["data"]["idx"], 4, "最新的是idx=4")


def test_event_broadcaster_no_subscribers():
    """测试4: 无订阅者时广播不报错"""
    print("\n--- 测试4: 无订阅者时广播不报错 ---")
    eb = EventBroadcaster()
    # 无订阅者，广播不应抛异常
    try:
        eb.broadcast("orphan", {"x": 1})
        assert_true(True, "无订阅者广播不报错")
    except Exception as e:
        assert_true(False, f"无订阅者广播不应报错: {e}")
    assert_eq(eb.get_stats()["total_events_broadcast"], 1, "事件计数仍增加")


def test_server_start_stop():
    """测试5: 服务器启动和停止"""
    print("\n--- 测试5: 服务器启动和停止 ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)  # port=0 自动分配
    server.start()
    assert_true(server.actual_port > 0, "服务器分配到端口")

    # 测试 /health 端点
    status, body = http_get(f"http://127.0.0.1:{server.actual_port}/health")
    assert_eq(status, 200, "/health 返回200")
    data = json.loads(body)
    assert_in("status", data, "/health 含 status 字段")

    server.stop()
    assert_true(True, "服务器正常停止")


def test_get_health():
    """测试6: GET /health"""
    print("\n--- 测试6: GET /health ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_get(f"http://127.0.0.1:{server.actual_port}/health")
        assert_eq(status, 200, "/health 状态码200")
        data = json.loads(body)
        assert_in("status", data, "含 status")
        assert_in("step_count", data, "含 step_count")
        assert_in("timestamp", data, "含 timestamp")
    finally:
        server.stop()


def test_get_status():
    """测试7: GET /status（含执行/策略/安全统计）"""
    print("\n--- 测试7: GET /status ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_get(f"http://127.0.0.1:{server.actual_port}/status")
        assert_eq(status, 200, "/status 状态码200")
        data = json.loads(body)
        assert_in("running", data, "含 running")
        assert_in("step_count", data, "含 step_count")
        assert_in("execution_stats", data, "含 execution_stats")
        assert_in("strategy_stats", data, "含 strategy_stats")
        assert_in("security_stats", data, "含 security_stats（阶段3集成）")
        assert_in("broadcaster_stats", data, "含 broadcaster_stats（阶段6新增）")
    finally:
        server.stop()


def test_get_metrics_prometheus():
    """测试8: GET /metrics（Prometheus格式）"""
    print("\n--- 测试8: GET /metrics Prometheus格式 ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_get(f"http://127.0.0.1:{server.actual_port}/metrics")
        assert_eq(status, 200, "/metrics 状态码200")
        assert_in("agent_steps_total", body, "含 agent_steps_total 指标")
        assert_in("agent_running", body, "含 agent_running 指标")
        assert_in("replay_buffer_size", body, "含 replay_buffer_size 指标")
        assert_in("# TYPE", body, "含 Prometheus TYPE 注释")
    finally:
        server.stop()


def test_get_dashboard():
    """测试9: GET / 返回Dashboard HTML"""
    print("\n--- 测试9: GET / Dashboard HTML ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_get(f"http://127.0.0.1:{server.actual_port}/")
        assert_eq(status, 200, "/ 状态码200")
        assert_in("<html", body.lower(), "返回HTML")
        assert_in("Self-Evolving Agent", body, "含标题")
        assert_in("EventSource", body, "含SSE客户端代码")
        assert_in("/status", body, "含API调用")
        assert_in("/events", body, "含SSE端点引用")
    finally:
        server.stop()


def test_get_tasks():
    """测试10: GET /tasks"""
    print("\n--- 测试10: GET /tasks ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_get(f"http://127.0.0.1:{server.actual_port}/tasks")
        assert_eq(status, 200, "/tasks 状态码200")
        data = json.loads(body)
        assert_in("pending_count", data, "含 pending_count")
        assert_in("tasks", data, "含 tasks 列表")
    finally:
        server.stop()


def test_get_strategy():
    """测试11: GET /strategy"""
    print("\n--- 测试11: GET /strategy ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_get(f"http://127.0.0.1:{server.actual_port}/strategy")
        assert_eq(status, 200, "/strategy 状态码200")
        data = json.loads(body)
        assert_in("total_strategies", data, "含 total_strategies")
    finally:
        server.stop()


def test_get_security():
    """测试12: GET /security"""
    print("\n--- 测试12: GET /security ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_get(f"http://127.0.0.1:{server.actual_port}/security")
        assert_eq(status, 200, "/security 状态码200")
        data = json.loads(body)
        assert_in("stats", data, "含 stats")
        assert_in("audit_log", data, "含 audit_log")
    finally:
        server.stop()


def test_get_decision_no_state():
    """测试13: GET /decision 无状态时返回409"""
    print("\n--- 测试13: GET /decision 无状态时返回409 ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_get(f"http://127.0.0.1:{server.actual_port}/decision")
        assert_eq(status, 409, "无current_state时返回409")
    finally:
        server.stop()


def test_get_decision_with_state():
    """测试14: GET /decision 有状态时返回决策"""
    print("\n--- 测试14: GET /decision 有状态时返回决策 ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    # 模拟设置 current_state（高CPU状态）
    agent.current_state = np.zeros(28)
    agent.current_state[0] = 95.0  # CPU 95%
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_get(f"http://127.0.0.1:{server.actual_port}/decision")
        assert_eq(status, 200, "/decision 有状态时返回200")
        data = json.loads(body)
        assert_in("fault_type", data, "含 fault_type")
        assert_in("action", data, "含 action")
        assert_in("reasoning", data, "含 reasoning（可解释性）")
    finally:
        server.stop()


def test_get_diagnose_no_state():
    """测试15: GET /diagnose 无状态时返回409"""
    print("\n--- 测试15: GET /diagnose 无状态时返回409 ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_get(f"http://127.0.0.1:{server.actual_port}/diagnose")
        assert_eq(status, 409, "无current_state时返回409")
    finally:
        server.stop()


def test_get_diagnose_with_state():
    """测试16: GET /diagnose 有状态时返回诊断"""
    print("\n--- 测试16: GET /diagnose 有状态时返回诊断 ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    agent.current_state = np.zeros(28)
    agent.current_state[0] = 90.0  # CPU 90%
    agent.current_state[10] = 85.0  # MEM 85%
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_get(f"http://127.0.0.1:{server.actual_port}/diagnose")
        assert_eq(status, 200, "/diagnose 有状态时返回200")
        data = json.loads(body)
        assert_in("metrics", data, "含 metrics")
        assert_in("anomaly", data, "含 anomaly")
        assert_in("diagnosis", data, "含 diagnosis")
        assert_true(data["metrics"]["cpu_percent"] == 90.0, "CPU指标正确提取")
    finally:
        server.stop()


def test_post_step():
    """测试17: POST /step 执行一步"""
    print("\n--- 测试17: POST /step ---")
    config = AgentConfig()
    config.main_loop_interval_ms = 100
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_post(f"http://127.0.0.1:{server.actual_port}/step")
        assert_eq(status, 200, "/step 状态码200")
        data = json.loads(body)
        # step 可能成功也可能返回error（取决于环境），但应该是有效JSON
        assert_true("step_count" in data or "error" in data, "返回含step_count或error")
    finally:
        server.stop()


def test_post_stop():
    """测试18: POST /stop 停止Agent"""
    print("\n--- 测试18: POST /stop ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_post(f"http://127.0.0.1:{server.actual_port}/stop")
        assert_eq(status, 200, "/stop 状态码200")
        data = json.loads(body)
        assert_eq(data["status"], "stopped", "返回 stopped")
    finally:
        server.stop()


def test_post_heal_no_state():
    """测试19: POST /heal 无状态时返回409"""
    print("\n--- 测试19: POST /heal 无状态时返回409 ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_post(f"http://127.0.0.1:{server.actual_port}/heal")
        assert_eq(status, 409, "无current_state时返回409")
    finally:
        server.stop()


def test_post_heal_with_state():
    """测试20: POST /heal 有状态时触发自愈"""
    print("\n--- 测试20: POST /heal 有状态时触发自愈 ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    agent.current_state = np.zeros(28)
    agent.current_state[0] = 95.0  # 高CPU触发异常
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_post(f"http://127.0.0.1:{server.actual_port}/heal")
        assert_eq(status, 200, "/heal 有状态时返回200")
        data = json.loads(body)
        assert_in("status", data, "含 status")
        # 可能是 healthy/healed/pending_approval/no_action
        assert_true(data["status"] in ["healthy", "healed", "pending_approval", "no_action"],
                    f"status 值合理: {data['status']}")
    finally:
        server.stop()


def test_post_validate_missing_params():
    """测试21: POST /validate 缺少参数返回400"""
    print("\n--- 测试21: POST /validate 缺少参数返回400 ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_post(f"http://127.0.0.1:{server.actual_port}/validate", body={})
        assert_eq(status, 400, "缺少参数返回400")
    finally:
        server.stop()


def test_404_unknown_path():
    """测试22: 未知路径返回404"""
    print("\n--- 测试22: 未知路径返回404 ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        status, body = http_get(f"http://127.0.0.1:{server.actual_port}/nonexistent")
        assert_eq(status, 404, "未知GET路径返回404")
        status, body = http_post(f"http://127.0.0.1:{server.actual_port}/nonexistent")
        assert_eq(status, 404, "未知POST路径返回404")
    finally:
        server.stop()


def test_backward_compat():
    """测试23: 向后兼容 — 原有端点仍可用"""
    print("\n--- 测试23: 向后兼容 ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        # 原有端点
        s1, _ = http_get(f"http://127.0.0.1:{server.actual_port}/health")
        assert_eq(s1, 200, "/health 仍可用")
        s2, _ = http_get(f"http://127.0.0.1:{server.actual_port}/status")
        assert_eq(s2, 200, "/status 仍可用")
        s3, _ = http_get(f"http://127.0.0.1:{server.actual_port}/metrics")
        assert_eq(s3, 200, "/metrics 仍可用")
        s4, _ = http_post(f"http://127.0.0.1:{server.actual_port}/step")
        assert_eq(s4, 200, "/step 仍可用")
        s5, _ = http_post(f"http://127.0.0.1:{server.actual_port}/stop")
        assert_eq(s5, 200, "/stop 仍可用")
    finally:
        server.stop()


def test_sse_event_stream():
    """测试24: SSE事件流推送"""
    print("\n--- 测试24: SSE事件流推送 ---")
    import socket
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    received_events = []
    error_occurred = []

    def sse_client():
        """SSE客户端：用原始socket连接并读取事件（避免urllib缓冲）"""
        try:
            sock = socket.create_connection(("127.0.0.1", server.actual_port), timeout=5)
            sock.sendall(b"GET /events HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            buffer = ""
            start = time.time()
            while time.time() - start < 3 and len(received_events) < 3:
                try:
                    sock.settimeout(1.0)
                    chunk = sock.recv(4096).decode("utf-8", errors="replace")
                    if not chunk:
                        break
                    buffer += chunk
                    while "\n\n" in buffer:
                        event_str, buffer = buffer.split("\n\n", 1)
                        for line in event_str.split("\n"):
                            if line.startswith("data: "):
                                data = line[6:]
                                try:
                                    event = json.loads(data)
                                    received_events.append(event)
                                except json.JSONDecodeError:
                                    pass
                except socket.timeout:
                    continue
            sock.close()
        except Exception as e:
            error_occurred.append(str(e))

    # 启动SSE客户端线程
    client_thread = threading.Thread(target=sse_client, daemon=True)
    client_thread.start()
    time.sleep(0.8)  # 等待客户端连接并接收connected事件

    # 广播事件
    server.broadcast("test_sse", {"msg": "event1"})
    server.broadcast("test_sse", {"msg": "event2"})

    client_thread.join(timeout=5)

    assert_true(len(error_occurred) == 0, f"SSE客户端无错误: {error_occurred}")
    assert_true(len(received_events) > 0, f"SSE收到事件 (count={len(received_events)})")
    # 第一个应该是 connected 事件
    if received_events:
        assert_eq(received_events[0]["type"], "connected", "首个事件是connected")
    # 应该收到广播的事件
    types = [e.get("type") for e in received_events]
    assert_in("test_sse", types, "广播的test_sse事件被收到")

    server.stop()


def test_broadcast_on_step():
    """测试25: POST /step 时广播事件"""
    print("\n--- 测试25: POST /step 时广播事件 ---")
    import socket
    config = AgentConfig()
    config.main_loop_interval_ms = 100
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()

    received = []

    def sse_listener():
        try:
            sock = socket.create_connection(("127.0.0.1", server.actual_port), timeout=5)
            sock.sendall(b"GET /events HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            buffer = ""
            start = time.time()
            while time.time() - start < 4 and len(received) < 10:
                try:
                    sock.settimeout(1.0)
                    chunk = sock.recv(4096).decode("utf-8", errors="replace")
                    if not chunk:
                        break
                    buffer += chunk
                    while "\n\n" in buffer:
                        event_str, buffer = buffer.split("\n\n", 1)
                        for line in event_str.split("\n"):
                            if line.startswith("data: "):
                                try:
                                    received.append(json.loads(line[6:]))
                                except json.JSONDecodeError:
                                    pass
                except socket.timeout:
                    continue
            sock.close()
        except Exception:
            pass

    listener = threading.Thread(target=sse_listener, daemon=True)
    listener.start()
    time.sleep(0.8)  # 等待SSE连接建立

    # 触发step，应广播事件
    http_post(f"http://127.0.0.1:{server.actual_port}/step")
    listener.join(timeout=4)

    types = [e.get("type") for e in received]
    assert_in("step", types, "step事件被广播")

    server.stop()


def test_server_broadcast_method():
    """测试26: AgentServer.broadcast 方法"""
    print("\n--- 测试26: AgentServer.broadcast 方法 ---")
    config = AgentConfig()
    agent = SelfEvolvingAgent(config)
    server = AgentServer(agent, port=0)
    server.start()
    try:
        # server.broadcast 应该等价于 server.broadcaster.broadcast
        server.broadcast("custom", {"x": 1})
        stats = server.broadcaster.get_stats()
        assert_eq(stats["total_events_broadcast"], 1, "broadcast方法递增事件计数")
    finally:
        server.stop()


# ============================================================================
# 主函数
# ============================================================================

def _cleanup_persistent_state():
    """清理测试产生的持久化状态（秩序化阶段1：测试数据隔离）"""
    import glob
    for f in ["./data/memory.db", "./data/goals_state.json"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    for pattern in ["./data/skills/*.py", "./data/checkpoints/*.json"]:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except OSError:
                pass


def main():
    _cleanup_persistent_state()
    print("=" * 60)
    print("阶段6测试：部署与对外API")
    print("=" * 60)

    tests = [
        test_event_broadcaster_basic,
        test_event_broadcaster_multi_subscribers,
        test_event_broadcaster_queue_full,
        test_event_broadcaster_no_subscribers,
        test_server_start_stop,
        test_get_health,
        test_get_status,
        test_get_metrics_prometheus,
        test_get_dashboard,
        test_get_tasks,
        test_get_strategy,
        test_get_security,
        test_get_decision_no_state,
        test_get_decision_with_state,
        test_get_diagnose_no_state,
        test_get_diagnose_with_state,
        test_post_step,
        test_post_stop,
        test_post_heal_no_state,
        test_post_heal_with_state,
        test_post_validate_missing_params,
        test_404_unknown_path,
        test_backward_compat,
        test_sse_event_stream,
        test_broadcast_on_step,
        test_server_broadcast_method,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            global failed
            failed += 1
            print(f"  [FAIL] {test.__name__} 抛出异常: {e}")
            import traceback
            traceback.print_exc()

    _cleanup_persistent_state()

    print("\n" + "=" * 60)
    print(f"  通过: {passed}, 失败: {failed}, 共{passed + failed}项")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
