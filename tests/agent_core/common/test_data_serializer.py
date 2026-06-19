"""
数据序列化模块测试。

覆盖：JSON往返、YAML往返、Protobuf往返、通用接口、不支持格式。
"""

import pytest

from agent_core.common.data_serializer import DataSerializer


class TestDataSerializer:
    """DataSerializer测试类。"""

    @pytest.fixture
    def serializer(self):
        """创建序列化器实例。"""
        return DataSerializer()

    def test_json_roundtrip(self, serializer):
        """测试JSON序列化往返。"""
        data = {"name": "test", "value": 42}
        text = serializer.to_json(data)
        assert isinstance(text, str)
        restored = serializer.from_json(text)
        assert restored == data

    def test_yaml_roundtrip(self, serializer):
        """测试YAML序列化往返。"""
        pytest.importorskip("yaml")
        data = {"name": "test", "value": 42}
        text = serializer.to_yaml(data)
        assert isinstance(text, str)
        restored = serializer.from_yaml(text)
        assert restored == data

    def test_yaml_fallback_to_json(self, serializer, monkeypatch):
        """测试YAML不可用时回退到JSON。"""
        monkeypatch.setitem(
            __import__("sys").modules, "yaml", None
        )
        data = {"key": "val"}
        text = serializer.to_yaml(data)
        assert text == serializer.to_json(data)

    def test_protobuf_roundtrip(self, serializer):
        """测试Protobuf序列化往返。"""
        pytest.importorskip("google.protobuf")
        data = {"name": "test", "value": 42.0}
        binary = serializer.to_protobuf(data)
        assert isinstance(binary, bytes)
        restored = serializer.from_protobuf(binary)
        assert restored == data

    def test_protobuf_not_available(self, serializer, monkeypatch):
        """测试Protobuf不可用时抛出异常。"""
        import sys
        monkeypatch.setitem(sys.modules, "google.protobuf.json_format", None)
        monkeypatch.setitem(sys.modules, "google.protobuf.struct_pb2", None)
        with pytest.raises(NotImplementedError):
            serializer.to_protobuf({"a": 1})

    def test_serialize_json(self, serializer):
        """测试通用接口JSON序列化。"""
        data = {"x": 1}
        result = serializer.serialize(data, "json")
        assert result == '{"x": 1}'

    def test_deserialize_json(self, serializer):
        """测试通用接口JSON反序列化。"""
        result = serializer.deserialize('{"x": 1}', "json")
        assert result == {"x": 1}

    def test_unsupported_format(self, serializer):
        """测试不支持格式抛出异常。"""
        with pytest.raises(ValueError, match="Unsupported"):
            serializer.serialize({}, "xml")
        with pytest.raises(ValueError, match="Unsupported"):
            serializer.deserialize("", "xml")
