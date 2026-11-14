"""把 115 云下载接成 MovieClaw 下载器适配器。

MovieClaw 只要求适配器回答四件事：提交、查询、删除、连接测试。这里把
「提交磁力 / ed2k」翻译成 115 离线任务，「查询」翻译成离线任务状态，
「完成」之后文件在 115 网盘里，由 p115-library 同步成 STRM。

约定（写进 README）：本地保存路径统一以 ``/media/115`` 开头，映射到 115
网盘的同一相对路径；不在这个前缀下的保存路径交给 115 默认目录。
"""

from __future__ import annotations

from typing import Callable

from movieclaw_downloader.base import BaseDownloader
from movieclaw_downloader.exceptions import (
    DownloaderAuthError,
    DownloaderConnectError,
    DownloaderNotSupportedError,
    DownloaderSubmitError,
    TorrentParseError,
)
from movieclaw_downloader.models import (
    DownloaderConfig,
    DownloaderInfo,
    DownloaderLimits,
    DownloadRequest,
    SubmitResult,
    TorrentBrief,
    TorrentFile,
    TorrentStatus,
)
from movieclaw_sdk.downloaders import compute_info_hash, parse_magnet_info_hash

from .client import (
    AuthExpired,
    Client115,
    NotFound,
    P115Error,
    RateLimited,
    Transient,
    ed2k_hash,
    magnet_hash,
)

#: 本地路径 → 115 目录的映射前缀（本地 /media/115/a/b 对应 115 网盘 /a/b）
LOCAL_ROOT = "/media/115"

_COMPLETED_STATES = {"done", "completed", "finished", "complete", "success", 2, "2"}
_FAILED_STATES = {"failed", "error", "3", 3}
_PAUSED_STATES = {"paused", "pause", "4", 4}
_QUEUED_STATES = {"waiting", "queued", "queue", "0", 0}


def _percent_of(task: dict) -> float:
    for key in ("percent", "percentDone", "percent_done", "progress"):
        if key in task:
            try:
                value = float(task[key])
            except (TypeError, ValueError):
                continue
            if 0.0 <= value <= 1.0 and value not in (0.0, 1.0):
                value *= 100.0
            return max(0.0, min(100.0, value))
    return 0.0


def _size_of(task: dict) -> int | None:
    for key in ("size", "file_size", "total_size", "size_bytes"):
        if key in task:
            try:
                return int(task[key])
            except (TypeError, ValueError):
                continue
    return None


def _name_of(task: dict) -> str:
    for key in ("name", "file_name", "title", "n"):
        value = task.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _files_of(task: dict) -> list[dict]:
    raw = task.get("files") or task.get("file_list") or []
    if isinstance(raw, dict):
        raw = raw.get("list") or []
    return [item for item in raw if isinstance(item, dict)]


def _state_of(task: dict, percent: float) -> tuple[str, bool]:
    raw = task.get("status", task.get("state"))
    key = raw.lower() if isinstance(raw, str) else raw
    if key in _COMPLETED_STATES or percent >= 100.0:
        return "completed", True
    if key in _FAILED_STATES:
        return "error", False
    if key in _PAUSED_STATES:
        return "paused", False
    if key in _QUEUED_STATES:
        return "queued", False
    return "downloading", False


def _translate(exc: P115Error, *, action: str) -> Exception:
    if isinstance(exc, AuthExpired):
        return DownloaderAuthError(str(exc))
    if isinstance(exc, (RateLimited, Transient)):
        return DownloaderConnectError(str(exc))
    return DownloaderSubmitError(f"115 {action}失败：{exc}")


class P115Downloader(BaseDownloader):
    def __init__(
        self,
        config: DownloaderConfig,
        client_factory: Callable[[DownloaderConfig], Client115] | None = None,
    ) -> None:
        super().__init__(config)
        self._factory = client_factory or (
            lambda cfg: Client115(cfg.password or "", timeout=cfg.timeout)
        )
        self._client: Client115 | None = None
        #: info_hash → 提交时的本地保存路径（115 不回报落盘路径，查询时补回去）
        self._paths: dict[str, str] = {}

    async def _get_client(self) -> Client115:
        if self._client is None:
            if not self.config.password:
                raise DownloaderAuthError(
                    "请在下载器配置的密码栏填写 115 Cookie"
                    "（UID=…; CID=…; SEID=…; KID=…）"
                )
            try:
                self._client = self._factory(self.config)
            except AuthExpired as exc:
                raise DownloaderAuthError(str(exc)) from exc
        return self._client

    # ------------------------------------------------------------------ 提交

    async def submit(self, request: DownloadRequest) -> SubmitResult:
        client = await self._get_client()

        if request.magnet is not None:
            url = request.magnet.strip()
            info_hash = (
                parse_magnet_info_hash(url)
                or magnet_hash(url)
                or ed2k_hash(url)
            )
            kind = "ed2k" if ed2k_hash(url) else "magnet"
            if kind == "ed2k":
                # ed2k 没有 infohash，用文件哈希当统一标识；115 用同一个哈希跟踪任务
                info_hash = ed2k_hash(url)
            elif info_hash is None:
                raise TorrentParseError("磁力链接里没有可用的 info_hash（btih）")
            wp_path_id, save_path = await self._resolve_target(client, request.save_path)
            try:
                await client.add_urls([url], wp_path_id=wp_path_id)
            except P115Error as exc:
                raise _translate(exc, action="提交云下载任务") from exc
            self._paths[info_hash] = save_path
            return SubmitResult(info_hash=info_hash, name="", already_exists=False)

        assert request.torrent_bytes is not None
        info_hash = compute_info_hash(request.torrent_bytes)
        wp_path_id, save_path = await self._resolve_target(client, request.save_path)
        try:
            await client.add_bt(info_hash, wp_path_id=wp_path_id)
        except P115Error as exc:
            raise _translate(exc, action="提交 BT 任务") from exc
        self._paths[info_hash] = save_path
        return SubmitResult(info_hash=info_hash, name="", already_exists=False)

    async def _resolve_target(
        self, client: Client115, save_path: str | None
    ) -> tuple[int | str | None, str]:
        """本地保存路径 → (115 目录 id, 查询时回填的保存路径)。"""
        path = (save_path or "").rstrip("/") or LOCAL_ROOT
        if path == LOCAL_ROOT or path.startswith(LOCAL_ROOT + "/"):
            rel = path[len(LOCAL_ROOT):].strip("/")
            try:
                cid = await client.ensure_dir(rel)
            except P115Error as exc:
                raise _translate(exc, action="定位 115 目录") from exc
            return cid, path
        # 不在约定前缀下的路径：交给 115 默认云下载目录，落盘位置以 115 为准
        return None, LOCAL_ROOT

    # ------------------------------------------------------------------ 查询

    async def get_torrent(
        self, info_hash: str, *, include_files: bool = True
    ) -> TorrentStatus | None:
        client = await self._get_client()
        try:
            task = await client.task(info_hash)
        except NotFound:
            return None
        except P115Error as exc:
            raise _translate(exc, action="查询任务") from exc

        percent = _percent_of(task)
        state, completed = _state_of(task, percent)
        size = _size_of(task)
        files: list[TorrentFile] = []
        if include_files:
            for index, item in enumerate(_files_of(task)):
                name = item.get("name") or item.get("file_name") or item.get("path") or ""
                item_size = _size_of(item) or 0
                if name:
                    files.append(TorrentFile(index=index, path=name, size_bytes=item_size))
            if not files:
                name = _name_of(task)
                if name:
                    files.append(TorrentFile(index=0, path=name, size_bytes=size or 0))
        completed_bytes = int(size * percent / 100) if size is not None else None
        return TorrentStatus(
            info_hash=info_hash,
            name=_name_of(task),
            progress=percent / 100.0,
            completed_bytes=completed_bytes,
            completed=completed,
            save_path=self._paths.get(info_hash, LOCAL_ROOT),
            files=files,
            size_bytes=size,
            state=state,
        )

    async def list_torrents(self) -> list[TorrentBrief]:
        client = await self._get_client()
        briefs: list[TorrentBrief] = []
        try:
            page, page_count = 1, 1
            while page <= min(page_count, 5):
                data = await client.tasks(page=page)
                page_count = data["page_count"] or 1
                for task in data["tasks"]:
                    info_hash = (task.get("info_hash") or "").lower()
                    if not info_hash:
                        continue
                    percent = _percent_of(task)
                    state, completed = _state_of(task, percent)
                    name = _name_of(task)
                    size = _size_of(task)
                    briefs.append(
                        TorrentBrief(
                            name=name,
                            content_name=name,
                            completed=completed,
                            info_hash=info_hash,
                            progress=percent / 100.0,
                            completed_bytes=int(size * percent / 100) if size else None,
                            size_bytes=size,
                            state=state,
                        )
                    )
                page += 1
        except P115Error as exc:
            raise _translate(exc, action="拉取任务列表") from exc
        return briefs

    # ------------------------------------------------------------------ 管理

    async def delete_torrent(self, info_hash: str, *, delete_files: bool = False) -> None:
        client = await self._get_client()
        try:
            await client.task_del(info_hash, delete_files=delete_files)
        except NotFound:
            return
        except P115Error as exc:
            raise _translate(exc, action="删除任务") from exc
        self._paths.pop(info_hash, None)

    async def set_location(self, info_hash: str, save_path: str) -> None:
        raise DownloaderNotSupportedError(
            "115 云下载不支持事后改保存目录；请在提交前把目标目录映射到 /media/115 下"
        )

    async def set_file_selection(self, info_hash: str, selected_indices: list[int]) -> None:
        raise DownloaderNotSupportedError("115 云下载不支持按文件索引选择性下载")

    async def resume(self, info_hash: str) -> None:
        client = await self._get_client()
        try:
            await client.task_resume(info_hash)
        except NotFound:
            return
        except P115Error as exc:
            raise _translate(exc, action="继续任务") from exc

    async def get_limits(self) -> DownloaderLimits:
        return DownloaderLimits()

    async def set_limits(self, limits: DownloaderLimits) -> None:
        # 115 云下载没有可写的全局限速 / 队列，静默忽略
        return None

    async def transfer_speeds(self) -> tuple[int, int]:
        return 0, 0

    async def set_download_limits(
        self, info_hashes: list[str], limit_bytes: int | None
    ) -> None:
        return None

    async def set_upload_limits(self, info_hashes: list[str], limit_bytes: int | None) -> None:
        return None

    async def test_connection(self) -> DownloaderInfo:
        client = await self._get_client()
        try:
            await client.ping()
        except P115Error as exc:
            raise _translate(exc, action="连接测试") from exc
        return DownloaderInfo(type="p115", version="115 网页接口")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
