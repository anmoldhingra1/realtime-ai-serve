"""Tests for StreamManager."""

import pytest

from realtime_serve.stream import StreamManager


class TestStreamManager:
    """Tests for stream lifecycle."""

    def test_init(self):
        mgr = StreamManager(default_timeout=10.0, buffer_size=50)
        assert mgr.default_timeout == 10.0
        assert mgr.buffer_size == 50

    def test_create_stream(self):
        mgr = StreamManager()
        gen = mgr.create_stream("s1")
        assert gen is not None
        assert "s1" in mgr._streams

    def test_duplicate_stream_raises(self):
        mgr = StreamManager()
        mgr.create_stream("s1")
        with pytest.raises(ValueError, match="already exists"):
            mgr.create_stream("s1")

    def test_stream_metadata(self):
        mgr = StreamManager(default_timeout=15.0)
        mgr.create_stream("s1")
        meta = mgr._streams["s1"]
        assert meta["closed"] is False
        assert meta["timeout"] == 15.0
        assert meta["token_count"] == 0

    def test_custom_timeout(self):
        mgr = StreamManager(default_timeout=10.0)
        mgr.create_stream("s1", timeout=60.0)
        assert mgr._streams["s1"]["timeout"] == 60.0
