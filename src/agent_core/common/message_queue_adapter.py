"""
消息队列适配器模块。

抽象消息队列接口，提供内存实现和Kafka/RabbitMQ预留适配器。

第一性原理：
- 消息队列是分布式系统的神经系统
- 适配器模式隔离具体中间件差异
- 内存实现用于测试和轻量级部署
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Callable, Coroutine, Dict, List, Optional

from agent_core.common.logger import get_logger


class MessageQueueAdapter(ABC):
    """消息队列适配器抽象基类。"""

    @abstractmethod
    async def publish(self, topic: str, message: bytes) -> bool:
        """发布消息。"""
        pass

    @abstractmethod
    async def subscribe(
        self, topic: str, handler: Callable[[bytes], Coroutine[Any, Any, None]]
    ) -> bool:
        """订阅消息。"""
        pass

    @abstractmethod
    async def unsubscribe(self, topic: str) -> bool:
        """取消订阅。"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭连接。"""
        pass


class InMemoryMessageQueue(MessageQueueAdapter):
    """
    内存消息队列。

    用于测试和轻量级部署，不支持持久化。
    """

    def __init__(self) -> None:
        self._topics: Dict[str, List[bytes]] = {}
        self._handlers: Dict[str, List[Callable[[bytes], Coroutine[Any, Any, None]]]] = {}
        self._logger = get_logger()

    async def publish(self, topic: str, message: bytes) -> bool:
        """发布消息到主题。"""
        if topic not in self._topics:
            self._topics[topic] = []
        self._topics[topic].append(message)
        handlers = self._handlers.get(topic, [])
        for handler in handlers:
            try:
                await handler(message)
            except Exception as exc:
                self._logger.error(f"[InMemoryMQ] Handler error: {exc}")
        return True

    async def subscribe(
        self, topic: str, handler: Callable[[bytes], Coroutine[Any, Any, None]]
    ) -> bool:
        """订阅主题。"""
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)
        self._logger.info(f"[InMemoryMQ] Subscribed to {topic}")
        return True

    async def unsubscribe(self, topic: str) -> bool:
        """取消订阅主题。"""
        self._handlers.pop(topic, None)
        return True

    async def close(self) -> None:
        """关闭队列。"""
        self._topics.clear()
        self._handlers.clear()

    def get_messages(self, topic: str) -> List[bytes]:
        """获取主题的所有消息（测试用）。"""
        return list(self._topics.get(topic, []))
