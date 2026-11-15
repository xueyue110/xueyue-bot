"""115 云下载下载器插件。

在 MovieClaw 里注册下载器类型 ``p115``：订阅或手动下载投递的磁力 / ed2k 链接
交给 115 离线下载，完成的文件落在 115 网盘目录，再由 p115-library 同步成 STRM。

另提供「待刮削目录」自动整理：配置环境变量后，后台循环把待刮削目录里新出现的
条目交给 MovieClaw 识别（dl.resolve-target），移入媒体库目录并触发扫描，
对应 mediary+flowlink 的「转存 → 识别 → 刮削 → 入库」链路。

登录：下载器配置的「密码」栏填 115 Cookie（``UID=…; CID=…; SEID=…; KID=…``），
「地址」栏填任意占位值（115 不需要服务地址）。
"""

from __future__ import annotations

import asyncio
import os

from pydantic import BaseModel, Field, SecretStr

from movieclaw_sdk import Context, plugin
from movieclaw_sdk.downloaders import DOWNLOADER_ADAPTERS, DownloaderAdapter
from movieclaw_sdk.ops import HOST_OPS

from .adapter import P115Downloader
from .client import Client115
from .watcher import Watcher


class Connection(BaseModel):
    url: str = Field(
        "local",
        title="占位地址",
        description="115 不需要填写服务地址，保留 local 即可",
        examples=["local"],
    )
    password: SecretStr | None = Field(
        None,
        title="115 Cookie",
        description="UID=…; CID=…; SEID=…; KID=…（浏览器登录 115 后从开发者工具复制）",
    )


ADAPTER = DownloaderAdapter(
    type="p115",
    title="115 云下载",
    factory=P115Downloader,
    connection=Connection,
)


async def _watch_loop(ctx: Context, watcher: Watcher, interval: int) -> None:
    """待刮削目录轮询循环；单次失败只记日志，不中断循环。"""
    while True:
        try:
            results = await watcher.tick()
            for item in results:
                ctx.logger.info("待刮削：%s → %s", item["entry"], item["status"])
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 后台循环不能因为一次失败停掉
            ctx.logger.exception("待刮削目录扫描失败")
        await asyncio.sleep(interval)


@plugin(
    "p115-download",
    title="115 云下载",
    disableable=True,
    reloadable=True,
    inject=(HOST_OPS,),
)
async def p115_download(ctx: Context) -> None:
    """注册 p115 下载器；配置了待刮削目录时再启动自动整理循环。"""
    ctx.contribute(DOWNLOADER_ADAPTERS, "p115", ADAPTER)

    staging = os.environ.get("P115_WATCH_STAGING")
    cookie = os.environ.get("P115_WATCH_COOKIE")
    if not staging or not cookie:
        return
    ops = await ctx.use(HOST_OPS).client(ctx)
    watcher = Watcher(Client115(cookie), ops, staging)
    interval = max(30, int(os.environ.get("P115_WATCH_INTERVAL", "300")))
    ctx.task(_watch_loop(ctx, watcher, interval), name="staging-watch")
