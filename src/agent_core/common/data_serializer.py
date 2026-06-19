"""
数据序列化模块。

支持JSON、YAML、Protobuf等多种数据格式的序列化和反序列化。

第一性原理：
- 数据格式是通信的契约，必须严格兼容
- 序列化必须可逆，不丢失信息
- 格式选择基于场景，JSON通用，Protobuf高效
"""

import json
from typing import Any, Dict, Optional

from agent_core.common.logger import get_logger


class DataSerializer:
    """
    数据序列化器。

    提供多种格式的序列化和反序列化方法。
    """

    def __init__(self) -> None:
        self._logger = get_logger()

    def to_json(self, data: Any) -> str:
        """
        序列化为JSON字符串。

        Args:
            data: 数据对象。

        Returns:
            JSON字符串。
        """
        return json.dumps(data, ensure_ascii=False, default=str)

    def from_json(self, text: str) -> Any:
        """
        从JSON字符串反序列化。

        Args:
            text: JSON字符串。

        Returns:
            数据对象。
        """
        return json.loads(text)

    def to_yaml(self, data: Any) -> str:
        """
        序列化为YAML字符串。

        Args:
            data: 数据对象。

        Returns:
            YAML字符串。
        """
        try:
            import yaml
            return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        except ImportError as exc:
            self._logger.warning("[DataSerializer] yaml not available, fallback to json")
            return self.to_json(data)

    def from_yaml(self, text: str) -> Any:
        """
        从YAML字符串反序列化。

        Args:
            text: YAML字符串。

        Returns:
            数据对象。
        """
        try:
            import yaml
            return yaml.safe_load(text)
        except ImportError as exc:
            self._logger.warning("[DataSerializer] yaml not available, fallback to json")
            return self.from_json(text)

    def to_protobuf(
        self, data: Dict[str, Any], message_type: Optional[str] = None
    ) -> bytes:
        """
        序列化为Protobuf字节。

        Args:
            data: 数据字典。
            message_type: 消息类型名称。

        Returns:
            Protobuf字节。

        Raises:
            NotImplementedError: 未安装protobuf时抛出。
        """
        try:
            import google.protobuf.json_format as pb_json
            import google.protobuf.struct_pb2 as struct_pb2
            msg = struct_pb2.Struct()
            pb_json.ParseDict(data, msg)
            return msg.SerializeToString()
        except ImportError as exc:
            self._logger.error("[DataSerializer] protobuf not available")
            raise NotImplementedError("protobuf support requires google-protobuf") from exc

    def from_protobuf(
        self, data: bytes, message_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        从Protobuf字节反序列化。

        Args:
            data: Protobuf字节。
            message_type: 消息类型名称。

        Returns:
            数据字典。

        Raises:
            NotImplementedError: 未安装protobuf时抛出。
        """
        try:
            import google.protobuf.json_format as pb_json
            import google.protobuf.struct_pb2 as struct_pb2
            msg = struct_pb2.Struct()
            msg.ParseFromString(data)
            return pb_json.MessageToDict(msg)
        except ImportError as exc:
            self._logger.error("[DataSerializer] protobuf not available")
            raise NotImplementedError("protobuf support requires google-protobuf") from exc

    def serialize(self, data: Any, format: str) -> Any:
        """
        按指定格式序列化。

        Args:
            data: 数据对象。
            format: 格式名称（json/yaml/protobuf）。

        Returns:
            序列化结果。
        """
        if format == "json":
            return self.to_json(data)
        if format == "yaml":
            return self.to_yaml(data)
        if format == "protobuf":
            return self.to_protobuf(data)
        raise ValueError(f"Unsupported format: {format}")

    def deserialize(self, data: Any, format: str) -> Any:
        """
        按指定格式反序列化。

        Args:
            data: 序列化数据。
            format: 格式名称。

        Returns:
            数据对象。
        """
        if format == "json":
            return self.from_json(data)
        if format == "yaml":
            return self.from_yaml(data)
        if format == "protobuf":
            return self.from_protobuf(data)
        raise ValueError(f"Unsupported format: {format}")
