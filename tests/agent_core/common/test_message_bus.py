"""
消息总线单元测试。

覆盖发布-订阅模式的四类用例。
"""

import asyncio
import unittest
from typing import Any, Dict, List

from agent_core.common.message_bus import MessageBus, get_message_bus


class TestMessageBus(unittest.TestCase):
    """测试消息总线。"""

    def setUp(self) -> None:
        """设置测试环境。"""
        self.received_messages: List[Any] = []

    def _callback(self, message: Any) -> None:
        self.received_messages.append(message)

    def test_singleton(self) -> None:
        """正常值入参测试：单例模式。"""
        bus_a = MessageBus()
        bus_b = MessageBus()
        self.assertIs(bus_a, bus_b)

    def test_subscribe_and_publish(self) -> None:
        """正常值入参测试：订阅与发布。"""
        bus = MessageBus()
        bus.subscribe("test_topic", self._callback)
        bus.publish("test_topic", {"key": "value"})
        self.assertEqual(len(self.received_messages), 1)
        self.assertEqual(self.received_messages[0]["key"], "value")

    def test_multiple_subscribers(self) -> None:
        """正常值入参测试：多订阅者。"""
        bus = MessageBus()
        messages_a: List[Any] = []
        messages_b: List[Any] = []
        bus.subscribe("topic", lambda m: messages_a.append(m))
        bus.subscribe("topic", lambda m: messages_b.append(m))
        bus.publish("topic", "message")
        self.assertEqual(len(messages_a), 1)
        self.assertEqual(len(messages_b), 1)

    def test_empty_topic(self) -> None:
        """空入参测试：无订阅者主题。"""
        bus = MessageBus()
        bus.publish("empty_topic", "message")

    def test_different_topics(self) -> None:
        """正常值入参测试：不同主题隔离。"""
        bus = MessageBus()
        bus.subscribe("topic_a", self._callback)
        bus.publish("topic_b", "message")
        self.assertEqual(len(self.received_messages), 0)

    def test_get_message_bus(self) -> None:
        """正常值入参测试：获取总线实例。"""
        bus = get_message_bus()
        self.assertIsInstance(bus, MessageBus)

    def test_publish_with_exception_in_callback(self) -> None:
        """异常测试：回调函数抛出异常不影响其他订阅者。"""
        bus = MessageBus()
        received: List[Any] = []

        def bad_callback(_msg: Any) -> None:
            raise ValueError("intentional error")

        bus.subscribe("topic", bad_callback)
        bus.subscribe("topic", lambda m: received.append(m))
        bus.publish("topic", "msg")
        self.assertEqual(len(received), 1)

    def test_subscribe_same_callback_twice(self) -> None:
        """边界测试：同一回调订阅两次会收到两次。"""
        bus = MessageBus()
        received: List[Any] = []
        cb = lambda m: received.append(m)
        bus.subscribe("topic", cb)
        bus.subscribe("topic", cb)
        bus.publish("topic", "x")
        self.assertEqual(len(received), 2)

    def test_publish_none_message(self) -> None:
        """边界测试：发布None消息。"""
        bus = MessageBus()
        received: List[Any] = []
        bus.subscribe("topic", lambda m: received.append(m))
        bus.publish("topic", None)
        self.assertEqual(len(received), 1)
        self.assertIsNone(received[0])


class TestMessageBusAsync(unittest.IsolatedAsyncioTestCase):
    """测试消息总线异步方法。"""

    async def test_start_and_stop(self) -> None:
        """正常值测试：启动和停止。"""
        bus = MessageBus()
        bus._running = False
        task = asyncio.create_task(bus.start())
        await asyncio.sleep(0.1)
        await bus.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def test_dispatch_async(self) -> None:
        """正常值测试：异步分发。"""
        bus = MessageBus()
        received: List[Any] = []
        bus.subscribe("topic", lambda m: received.append(m))
        await bus._dispatch("topic", "hello")
        self.assertEqual(len(received), 1)

    async def test_dispatch_with_exception(self) -> None:
        """异常测试：异步分发中回调异常。"""
        bus = MessageBus()

        def bad_callback(_msg: Any) -> None:
            raise RuntimeError("async error")

        bus.subscribe("topic", bad_callback)
        await bus._dispatch("topic", "msg")


if __name__ == "__main__":
    unittest.main()
