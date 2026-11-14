from __future__ import annotations

import asyncio

import httpx
import pytest

from movieclaw_downloader.exceptions import (
    DownloaderAuthError,
    DownloaderConnectError,
    DownloaderNotSupportedError,
    TorrentParseError,
)
from movieclaw_downloader.models import DownloaderConfig, DownloadRequest
from movieclaw_sdk.downloaders import compute_info_hash

from fake115 import Fake115
from p115_download.adapter import LOCAL_ROOT, P115Downloader
from p115_download.client import Client115

COOKIE = "UID=uid1; CID=cid1; SEID=seid1; KID=kid1"
HASH = "a" * 40
ED2K_HASH = "b" * 32


def make(fake: Fake115 | None = None, password: str | None = COOKIE):
    fake = fake or Fake115()
    config = DownloaderConfig(type="p115", url="local", password=password, timeout=5)
    adapter = P115Downloader(
        config,
        client_factory=lambda cfg: Client115(
            cfg.password or "", timeout=cfg.timeout, transport=httpx.MockTransport(fake.handler)
        ),
    )
    return adapter, fake


def test_missing_cookie_raises_auth_error():
    async def scenario():
        adapter, _ = make(password=None)
        with pytest.raises(DownloaderAuthError):
            await adapter.submit(DownloadRequest(magnet=f"magnet:?xt=urn:btih:{HASH}"))

    asyncio.run(scenario())


def test_submit_magnet_creates_task_and_maps_directory():
    async def scenario():
        adapter, fake = make()
        result = await adapter.submit(
            DownloadRequest(
                magnet=f"magnet:?xt=urn:btih:{HASH}&dn=Movie",
                save_path=f"{LOCAL_ROOT}/电影/新片",
            )
        )
        assert result.info_hash == HASH
        assert HASH in fake.tasks
        # /media/115/电影/新片 → 115 根下逐级建目录
        assert "电影" in fake.dirs["0"]
        movie_cid = fake.dirs["0"]["电影"]
        assert "新片" in fake.dirs[movie_cid]

    asyncio.run(scenario())


def test_progress_then_complete():
    async def scenario():
        adapter, fake = make()
        await adapter.submit(
            DownloadRequest(magnet=f"magnet:?xt=urn:btih:{HASH}&dn=Show", save_path=f"{LOCAL_ROOT}/剧集")
        )
        status = await adapter.get_torrent(HASH)
        assert status is not None
        assert status.completed is False
        assert status.progress == 0.0
        assert status.save_path == f"{LOCAL_ROOT}/剧集"

        fake.set_percent(HASH, 50)
        status = await adapter.get_torrent(HASH)
        assert status.progress == 0.5
        assert status.completed_bytes == 1024  # size 2048 * 50%

        fake.complete(HASH)
        status = await adapter.get_torrent(HASH)
        assert status.completed is True
        assert status.progress == 1.0
        assert status.state == "completed"
        assert status.files and status.files[0].size_bytes == 2048

    asyncio.run(scenario())


def test_submit_ed2k_uses_ed2k_hash():
    async def scenario():
        adapter, fake = make()
        url = f"ed2k://|file|movie.mkv|2048|{ED2K_HASH.upper()}|/"
        result = await adapter.submit(DownloadRequest(magnet=url, save_path=f"{LOCAL_ROOT}/电影"))
        assert result.info_hash == ED2K_HASH
        assert ED2K_HASH in fake.tasks

    asyncio.run(scenario())


def test_submit_torrent_bytes_uses_add_bt():
    async def scenario():
        adapter, fake = make()
        torrent = b"d4:infod4:name1:x6:lengthi0eee"
        expected = compute_info_hash(torrent)
        result = await adapter.submit(
            DownloadRequest(torrent_bytes=torrent, save_path=f"{LOCAL_ROOT}/电影")
        )
        assert result.info_hash == expected
        assert expected in fake.tasks

    asyncio.run(scenario())


def test_magnet_without_hash_raises_parse_error():
    async def scenario():
        adapter, _ = make()
        with pytest.raises(TorrentParseError):
            await adapter.submit(DownloadRequest(magnet="magnet:?dn=no-hash"))

    asyncio.run(scenario())


def test_unknown_hash_returns_none():
    async def scenario():
        adapter, _ = make()
        assert await adapter.get_torrent("f" * 40) is None

    asyncio.run(scenario())


def test_list_and_delete():
    async def scenario():
        adapter, fake = make()
        await adapter.submit(DownloadRequest(magnet=f"magnet:?xt=urn:btih:{HASH}&dn=A", save_path=LOCAL_ROOT))
        briefs = await adapter.list_torrents()
        assert [b.info_hash for b in briefs] == [HASH]
        await adapter.delete_torrent(HASH)
        assert HASH not in fake.tasks
        # 幂等：再删一次不报错
        await adapter.delete_torrent(HASH)

    asyncio.run(scenario())


def test_expired_cookie_maps_to_auth_error():
    async def scenario():
        adapter, fake = make()
        fake.error = {"state": False, "code": 40101017, "message": "登录已失效"}
        with pytest.raises(DownloaderAuthError):
            await adapter.submit(DownloadRequest(magnet=f"magnet:?xt=urn:btih:{HASH}"))

    asyncio.run(scenario())


def test_rate_limited_maps_to_connect_error():
    async def scenario():
        adapter, fake = make()
        fake.rate_limited = True
        with pytest.raises(DownloaderConnectError):
            await adapter.submit(DownloadRequest(magnet=f"magnet:?xt=urn:btih:{HASH}"))

    asyncio.run(scenario())


def test_save_path_outside_prefix_falls_back_to_default_dir():
    async def scenario():
        adapter, fake = make()
        await adapter.submit(DownloadRequest(magnet=f"magnet:?xt=urn:btih:{HASH}&dn=X", save_path="/downloads/foo"))
        status = await adapter.get_torrent(HASH)
        assert status.save_path == LOCAL_ROOT

    asyncio.run(scenario())


def test_set_location_not_supported():
    async def scenario():
        adapter, _ = make()
        with pytest.raises(DownloaderNotSupportedError):
            await adapter.set_location(HASH, "/media/115/x")

    asyncio.run(scenario())


def test_connection_reports_type():
    async def scenario():
        adapter, _ = make()
        info = await adapter.test_connection()
        assert info.type == "p115"

    asyncio.run(scenario())
