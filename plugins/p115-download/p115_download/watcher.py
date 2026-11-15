"""115 待刮削目录 → 识别 → 移入媒体库 → 触发扫描 的自动整理循环。

不依赖挂载：用 115 网页接口列待刮削目录，识别交给宿主的 ``dl.resolve-target``
操作，搬移用 115 的 files/move，最后对目标目录触发 ``library.scan.start``
（cloud_paths），由 MovieClaw 完成刮削入账、p115-library 生成 STRM。
"""

from __future__ import annotations

import re

#: 剧集特征：S01E02 / E02 / 第3集
_TV = re.compile(r"(?i)(S\d{1,3}E\d{1,4}|(?<![A-Za-z])E\d{1,4}(?![A-Za-z])|第\s*\d+\s*[集季])")
_VIDEO_EXT = re.compile(r"(?i)\.(mkv|mp4|avi|ts|m2ts|iso|rmvb|mov|wmv|flv|webm)$")

#: 发布名里的技术标记：遇到第一个就截断，剩下的留给识别
_RELEASE_TAGS = {
    "2160p", "1080p", "720p", "480p", "4k", "8k", "uhd",
    "web", "webdl", "web-dl", "webrip", "bluray", "blu-ray", "remux", "hdrip", "brrip",
    "hdr", "hdr10", "hdr10+", "dv", "dolby", "dovi", "sdr",
    "x264", "x265", "h264", "h265", "hevc", "avc", "10bit", "8bit",
    "aac", "ac3", "eac3", "dts", "truehd", "atmos", "flac",
    "nf", "amzn", "dsnp", "hmax", "atvp", "ma",
}


def guess_kind(name: str) -> str:
    return "tv" if _TV.search(name or "") else "movie"


def guess_title(name: str) -> str:
    stem = _VIDEO_EXT.sub("", name or "").strip()
    stem = re.sub(r"[._]+", " ", stem)
    stem = re.sub(r"\s{2,}", " ", stem).strip()
    kept: list[str] = []
    for token in stem.split(" "):
        low = token.lower().strip("[]()-")
        if low in _RELEASE_TAGS or re.fullmatch(r"\d{3,4}p", low):
            break
        kept.append(token)
    return " ".join(kept).strip(" -[]()") or (name or "").strip()


class Watcher:
    """轮询待刮削目录，把新条目识别并搬进媒体库。"""

    def __init__(self, client, ops, staging_path: str, *, processed: set[str] | None = None) -> None:
        self.client = client
        self.ops = ops
        self.staging_path = staging_path
        self.processed: set[str] = processed if processed is not None else set()

    async def tick(self) -> list[dict]:
        cid = await self.client.resolve_dir(self.staging_path)
        entries = await self.client.list_entries(cid)
        results = []
        for entry in entries:
            if entry["id"] in self.processed:
                continue
            results.append(await self.handle(entry))
        return results

    async def handle(self, entry: dict) -> dict:
        name = entry["name"]
        kind = guess_kind(name)
        title = guess_title(name)
        plan = await self.ops.call(
            "dl.resolve-target",
            {"kind": kind, "title": title, "hint": title, "subtitle": name},
        )
        plan = plan or {}
        if plan.get("status") in ("not_found", "ambiguous") or not plan.get("library_id"):
            self.processed.add(entry["id"])
            return {"entry": name, "status": "needs_attention", "reason": plan.get("status")}

        root = (plan.get("cloud_root_path") or "").strip("/")
        entry_dir = plan.get("entry_dir_name") or title
        target_path = "/" + "/".join(part for part in (root, entry_dir) if part)
        target_cid = await self.client.ensure_dir(target_path)
        await self.client.move([entry["id"]], target_cid)
        await self.ops.call(
            "library.scan.start",
            {"library_id": plan["library_id"], "body": {"cloud_paths": [target_path]}},
        )
        self.processed.add(entry["id"])
        return {"entry": name, "status": "moved", "target": target_path}
