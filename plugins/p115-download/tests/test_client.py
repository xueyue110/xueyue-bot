from __future__ import annotations

import asyncio

import httpx

from fake115 import Fake115
from p115_download.client import Client115, pick_cookies


def make_client(fake: Fake115) -> Client115:
    return Client115(
        "UID=uid1; CID=cid1; SEID=seid1; KID=kid1",
        timeout=5,
        transport=httpx.MockTransport(fake.handler),
    )


def test_pick_cookies_only_login_keys():
    found = pick_cookies("a=1; UID=u; CID=c; SEID=s; KID=k; b=2")
    assert found == {"UID": "u", "CID": "c", "SEID": "s", "KID": "k"}


def test_ensure_dir_creates_and_reuses():
    async def scenario():
        fake = Fake115()
        client = make_client(fake)
        try:
            first = await client.ensure_dir("电影/新片")
            second = await client.ensure_dir("电影/新片")
            assert first == second
            assert len(fake.dirs["0"]) == 1
        finally:
            await client.aclose()

    asyncio.run(scenario())


def test_ping_uses_files_endpoint():
    async def scenario():
        client = make_client(Fake115())
        try:
            await client.ping()
        finally:
            await client.aclose()

    asyncio.run(scenario())


def test_task_list_shape():
    async def scenario():
        fake = Fake115()
        client = make_client(fake)
        try:
            fake.tasks["c" * 40] = {
                "info_hash": "c" * 40,
                "name": "T",
                "size": 10,
                "percent": 100,
                "status": "done",
            }
            page = await client.tasks(page=1)
            assert page["count"] == 1
            assert page["tasks"][0]["info_hash"] == "c" * 40
        finally:
            await client.aclose()

    asyncio.run(scenario())
