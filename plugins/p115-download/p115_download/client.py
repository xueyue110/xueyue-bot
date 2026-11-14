"""115 网页接口客户端（Cookie 登录）：云下载（离线）任务 + 文件目录。

只覆盖下载器需要的最小面：加任务、查任务、删/暂停/继续任务、配额、
目录定位（供本地路径 → 115 目录 id 映射）。接口路径以 p115client（MIT）
的实现为准，参数按 115 现行网页接口。
"""

from __future__ import annotations

import re

import httpx

WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
COOKIE_KEYS = ("UID", "CID", "SEID", "KID")

#: 确认登录失效的错误码（限流、风控、网络错误都不算）
AUTH_CODES = frozenset(
    {
        99,
        911,
        990001,
        40101009,
        40101010,
        40101017,
        40101032,
        40140116,
        40140117,
        40140119,
        40140120,
        40140125,
    }
)


class P115Error(Exception):
    """115 拒绝了这个操作。"""


class AuthExpired(P115Error):
    """Cookie 失效，必须重新登录。"""


class RateLimited(P115Error):
    """明确限流：延后重试，不要提示重新登录。"""

    def __init__(self, message: str = "115 请求过于频繁，稍后自动重试", *, retry_after: int = 60) -> None:
        super().__init__(message)
        self.retry_after = max(1, min(3600, int(retry_after)))


class Transient(P115Error):
    """网络 / 5xx，重试即可。"""


class NotFound(P115Error):
    """任务或目录不存在。"""


_ED2K = re.compile(r"ed2k://\|file\|[^|]+\|(\d+)\|([a-fA-F0-9]{32})\|/", re.I)
_MAGNET_HASH = re.compile(r"btih:([a-fA-F0-9]{40})", re.I)


def pick_cookies(header: str) -> dict[str, str]:
    """从整段 Cookie 里挑出登录态的四项。"""
    found: dict[str, str] = {}
    for part in (header or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name in COOKIE_KEYS and value:
            found[name] = value
    return found


def magnet_hash(url: str) -> str | None:
    match = _MAGNET_HASH.search(url or "")
    return match.group(1).lower() if match else None


def ed2k_hash(url: str) -> str | None:
    match = _ED2K.search(url or "")
    return match.group(2).lower() if match else None


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class Client115:
    """Cookie 登录的 115 网页接口客户端。"""

    def __init__(
        self,
        cookie: str,
        *,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        base_cloud: str = "https://clouddownload.115.com",
        base_files: str = "https://webapi.115.com",
        base_web: str = "https://115.com",
    ) -> None:
        self.cookies = pick_cookies(cookie)
        if not self.cookies.get("UID") or not self.cookies.get("SEID"):
            raise AuthExpired("Cookie 不完整：需要 UID、CID、SEID、KID 四项，请重新复制")
        self._base_cloud = base_cloud
        self._base_files = base_files
        self._base_web = base_web
        self._http = httpx.AsyncClient(
            cookies=self.cookies,
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
            headers={"User-Agent": WEB_UA, "Referer": "https://115.com/"},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------ 请求与校验

    async def _request(self, url: str, *, method: str = "GET", data=None, params=None) -> dict:
        try:
            resp = await self._http.request(method, url, data=data, params=params)
        except httpx.HTTPError as exc:
            raise Transient(f"115 网络请求失败：{exc}") from exc
        if resp.status_code in (401, 403):
            raise AuthExpired("115 登录已失效，请更新 Cookie")
        if resp.status_code in (405, 429):
            retry_after = _as_int(resp.headers.get("Retry-After")) or 60
            raise RateLimited(retry_after=retry_after)
        if resp.status_code >= 500:
            raise Transient(f"115 暂时不可用（HTTP {resp.status_code}）")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise Transient("115 返回了非 JSON 内容") from exc
        return self._check(payload)

    @staticmethod
    def _check(payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise P115Error("115 返回了认不出的内容")
        state = payload.get("state")
        if state in (True, 1) or ("state" not in payload and "data" in payload):
            return payload
        code = payload.get("code") or payload.get("errno") or payload.get("errNo")
        code_int = _as_int(code)
        message = str(payload.get("message") or payload.get("error") or payload.get("errmsg") or "").strip()
        if any(word in message for word in ("验证码", "安全验证", "风控", "captcha")):
            raise P115Error("115 要求安全验证，请在官方客户端完成验证后重试")
        if any(word in message for word in ("频繁", "限流", "频率限制", "稍后")):
            raise RateLimited()
        if code_int in AUTH_CODES:
            raise AuthExpired(f"115 登录已失效（{message or code_int}），请更新 Cookie")
        raise P115Error(message or f"115 返回错误码 {code_int}")

    async def _cloud(self, action: str, *, method: str = "GET", payload: dict | None = None) -> dict:
        params = dict(payload or {})
        params["ac"] = action
        url = f"{self._base_cloud}/web/"
        if method.upper() == "POST":
            return await self._request(url, method="POST", data=params)
        return await self._request(url, method="GET", params=params)

    # ------------------------------------------------------------------ 登录 / 配额

    async def ping(self) -> dict:
        """用文件列表接口验证 Cookie 是否有效。"""
        return await self._request(f"{self._base_files}/files", params={"aid": 1, "limit": 1, "cid": 0})

    async def quota(self) -> dict:
        data = await self._cloud("get_quota_info")
        return data.get("data") or {}

    # ------------------------------------------------------------------ 任务

    async def add_urls(self, urls: list[str], *, wp_path_id=None, savepath: str | None = None) -> dict:
        payload: dict = {f"url[{i}]": url for i, url in enumerate(urls)}
        if wp_path_id is not None:
            payload["wp_path_id"] = str(wp_path_id)
        if savepath:
            payload["savepath"] = savepath
        data = await self._cloud("add_task_urls", method="POST", payload=payload)
        return data.get("data") or {}

    async def add_bt(self, info_hash: str, *, wp_path_id=None, savepath: str | None = None) -> dict:
        payload: dict = {"info_hash": info_hash}
        if wp_path_id is not None:
            payload["wp_path_id"] = str(wp_path_id)
        if savepath:
            payload["savepath"] = savepath
        data = await self._cloud("add_task_bt", method="POST", payload=payload)
        return data.get("data") or {}

    async def task(self, info_hash: str) -> dict:
        """单个任务详情；不存在时抛 NotFound。"""
        data = await self._cloud("get_user_task", payload={"info_hash": info_hash})
        body = data.get("data") or {}
        if not body:
            raise NotFound(f"115 里没有这个任务：{info_hash}")
        return body

    async def tasks(self, page: int = 1, page_size: int = 30) -> dict:
        """一页任务：返回 {tasks, count, page, page_count}。"""
        data = await self._cloud(
            "get_task_list", payload={"page": page, "page_size": page_size}
        )
        body = data.get("data") or {}
        return {
            "tasks": body.get("tasks") or [],
            "count": _as_int(body.get("count")) or 0,
            "page": _as_int(body.get("page")) or page,
            "page_count": _as_int(body.get("page_count")) or 1,
        }

    async def task_del(self, info_hash: str, *, delete_files: bool = False) -> None:
        await self._cloud(
            "task_del",
            method="POST",
            payload={"info_hash[0]": info_hash, "del_source_file": 1 if delete_files else 0},
        )

    async def task_pause(self, info_hash: str) -> None:
        await self._cloud("task_pause", method="POST", payload={"info_hash[0]": info_hash})

    async def task_resume(self, info_hash: str) -> None:
        await self._cloud("task_resume", method="POST", payload={"info_hash[0]": info_hash})

    # ------------------------------------------------------------------ 目录

    async def _list_dirs(self, cid) -> dict[str, int | str]:
        data = await self._request(
            f"{self._base_files}/files",
            params={"aid": 1, "cid": cid, "show_dir": 1, "limit": 1150, "offset": 0},
        )
        items = data.get("data") or []
        if isinstance(items, dict):
            items = items.get("list") or []
        dirs: dict[str, int | str] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            if "cid" in item and "fid" not in item:
                name = item.get("n") or item.get("name") or ""
                if name:
                    dirs[name] = item["cid"]
        return dirs

    async def _mkdir(self, pid, name: str) -> int | str:
        data = await self._request(
            f"{self._base_files}/files/add",
            method="POST",
            data={"pid": str(pid), "cname": name},
        )
        body = data.get("data") or {}
        cid = body.get("cid") if isinstance(body, dict) else None
        if cid is None:
            raise P115Error(f"115 建目录失败：{name}")
        return cid

    async def ensure_dir(self, rel_path: str) -> int | str:
        """把相对路径逐级解析成 115 目录 id，缺的目录自动创建。"""
        cid: int | str = "0"
        for part in [p for p in rel_path.split("/") if p]:
            dirs = await self._list_dirs(cid)
            if part in dirs:
                cid = dirs[part]
            else:
                cid = await self._mkdir(cid, part)
        return cid
