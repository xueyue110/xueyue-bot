"""115 云下载下载器插件。

在 MovieClaw 里注册下载器类型 ``p115``：订阅或手动下载投递的磁力 / ed2k 链接
交给 115 离线下载，完成的文件落在 115 网盘目录，再由 p115-library 同步成 STRM。

登录：下载器配置的「密码」栏填 115 网页 Cookie（``UID=…; CID=…; SEID=…; KID=…``），
「地址」栏填任意占位值（115 不需要服务地址）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr

from movieclaw_sdk import Context, plugin
from movieclaw_sdk.downloaders import DOWNLOADER_ADAPTERS, DownloaderAdapter

from .adapter import P115Downloader


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


@plugin("p115-download", title="115 云下载", disableable=True, reloadable=True)
async def p115_download(ctx: Context) -> None:
    """注册 p115 下载器：磁力/ed2k 投 115 离线，成功后交给 p115-library 出 STRM。"""
    ctx.contribute(DOWNLOADER_ADAPTERS, "p115", ADAPTER)
