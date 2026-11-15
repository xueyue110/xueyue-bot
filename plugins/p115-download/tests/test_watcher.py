from __future__ import annotations

import asyncio

import httpx

from fake115 import Fake115
from p115_download.client import Client115
from p115_download.watcher import Watcher, guess_kind, guess_title

COOKIE = "UID=uid1; CID=cid1; SEID=seid1; KID=kid1"
PLAN = {
    "status": "ok",
    "library_id": 7,
    "library_name": "电影",
    "cloud_root_path": "/媒体库",
    "entry_dir_name": "三体 (2023)",
}


class FakeOps:
    def __init__(self, plan: dict | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.plan = plan or dict(PLAN)

    async def call(self, op: str, args: dict):
        self.calls.append((op, args))
        if op == "dl.resolve-target":
            return self.plan
        if op == "library.scan.start":
            return {"job_id": "job-1"}
        raise AssertionError(f"unexpected op {op}")


def make(plan: dict | None = None):
    fake = Fake115()
    staging = fake.add_dir("待刮削")
    client = Client115(COOKIE, timeout=5, transport=httpx.MockTransport(fake.handler))
    ops = FakeOps(plan)
    watcher = Watcher(client, ops, "/待刮削")
    return watcher, fake, ops, staging, client


def find_dir(fake: Fake115, parent: str, name: str) -> str:
    return fake.dirs[parent][name]


def test_guess_helpers():
    assert guess_kind("三体.S01E01.1080p.mkv") == "tv"
    assert guess_kind("流浪地球2.2023.2160p.mkv") == "movie"
    assert guess_title("流浪地球2.2023.2160p.mkv") == "流浪地球2 2023"
    assert guess_kind("Show.E05.mkv") == "tv"


def test_tick_moves_new_file_and_scans():
    async def scenario():
        watcher, fake, ops, staging, client = make()
        fake.add_file(staging, "f1", "三体.S01E01.1080p.mkv", 4096)
        try:
            results = await watcher.tick()
            assert results == [
                {"entry": "三体.S01E01.1080p.mkv", "status": "moved", "target": "/媒体库/三体 (2023)"}
            ]
            # 目录已建、文件已移动
            media = find_dir(fake, "0", "媒体库")
            entry = find_dir(fake, media, "三体 (2023)")
            assert "f1" in fake.files[entry]
            # 识别用 tv、扫描只扫目标目录
            op1, args1 = ops.calls[0]
            assert op1 == "dl.resolve-target" and args1["kind"] == "tv"
            op2, args2 = ops.calls[1]
            assert op2 == "library.scan.start"
            assert args2["library_id"] == 7
            assert args2["body"]["cloud_paths"] == ["/媒体库/三体 (2023)"]
        finally:
            await client.aclose()

    asyncio.run(scenario())


def test_second_tick_skips_processed():
    async def scenario():
        watcher, fake, ops, staging, client = make()
        fake.add_file(staging, "f1", "流浪地球2.2023.2160p.mkv")
        try:
            await watcher.tick()
            calls_after_first = len(ops.calls)
            await watcher.tick()
            assert len(ops.calls) == calls_after_first
        finally:
            await client.aclose()

    asyncio.run(scenario())


def test_unresolved_item_needs_attention_and_stays():
    async def scenario():
        watcher, fake, ops, staging, client = make({"status": "not_found", "candidates": []})
        fake.add_file(staging, "f1", "unknown.release.mkv")
        try:
            results = await watcher.tick()
            assert results[0]["status"] == "needs_attention"
            assert "f1" in fake.files[staging]
            assert [c[0] for c in ops.calls] == ["dl.resolve-target"]
        finally:
            await client.aclose()

    asyncio.run(scenario())


def test_tick_handles_folder_entry():
    async def scenario():
        watcher, fake, ops, staging, client = make()
        folder = fake.add_dir("三体.S01E01", staging)
        try:
            results = await watcher.tick()
            assert results[0]["status"] == "moved"
            media = find_dir(fake, "0", "媒体库")
            entry = find_dir(fake, media, "三体 (2023)")
            assert folder in fake.dirs[entry].values()
        finally:
            await client.aclose()

    asyncio.run(scenario())
