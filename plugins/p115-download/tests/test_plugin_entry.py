from __future__ import annotations

from p115_download import ADAPTER


def test_adapter_metadata():
    assert ADAPTER.type == "p115"
    assert ADAPTER.title == "115 云下载"


def test_connection_schema_has_cookie_field():
    fields = ADAPTER.connection.model_fields
    assert "url" in fields
    assert "password" in fields
