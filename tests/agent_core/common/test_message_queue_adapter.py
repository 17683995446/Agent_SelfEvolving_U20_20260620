"""
消息队列适配器测试。

覆盖：发布订阅、消息传递、取消订阅、关闭、多订阅者。
"""

import pytest

from agent_core.common.message_queue_adapter import InMemoryMessageQueue


class TestInMemoryMessageQueue:
    """InMemoryMessageQueue测试类。"""

    @pytest.fixture
    def mq(self):
        """创建内存队列实例。"""
        return InMemoryMessageQueue()

    @pytest.mark.asyncio
    async def test_publish_and_get(self, mq):
        """测试发布和获取消息。"""
        await mq.publish("test", b"hello")
        msgs = mq.get_messages("test")
        assert msgs == [b"hello"]

    @pytest.mark.asyncio
    async def test_subscribe_and_receive(self, mq):
        """测试订阅并接收消息。"""
        received = []
        async def handler(msg):
            received.append(msg)
        await mq.subscribe("test", handler)
        await mq.publish("test", b"world")
        assert received == [b"world"]

    @pytest.mark.asyncio
    async def test_unsubscribe(self, mq):
        """测试取消订阅。"""
        received = []
        async def handler(msg):
            received.append(msg)
        await mq.subscribe("test", handler)
        await mq.unsubscribe("test")
        await mq.publish("test", b"msg")
        assert received == []

    @pytest.mark.asyncio
    async def test_close(self, mq):
        """测试关闭清空数据。"""
        await mq.publish("test", b"msg")
        await mq.close()
        assert mq.get_messages("test") == []

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, mq):
        """测试多订阅者。"""
        received1 = []
        received2 = []
        async def h1(msg):
            received1.append(msg)
        async def h2(msg):
            received2.append(msg)
        await mq.subscribe("test", h1)
        await mq.subscribe("test", h2)
        await mq.publish("test", b"broadcast")
        assert received1 == [b"broadcast"]
        assert received2 == [b"broadcast"]

    @pytest.mark.asyncio
    async def test_handler_error_does_not_break(self, mq):
        """测试处理器错误不影响其他处理器。"""
        received = []
        async def bad_handler(msg):
            raise ValueError("boom")
        async def good_handler(msg):
            received.append(msg)
        await mq.subscribe("test", bad_handler)
        await mq.subscribe("test", good_handler)
        await mq.publish("test", b"msg")
        assert received == [b"msg"]
