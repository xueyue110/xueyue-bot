"""假 115 后端：用 httpx.MockTransport 模拟云下载与文件接口。

只实现适配器用到的端点，够验证状态机与路径映射，不连真 115。
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs

import httpx

MAGNET = re.compile(r"btih:([a-fA-F0-9]{40})", re.I)
ED2K = re.compile(r"ed2k://\|file\|([^|]+)\|(\d+)\|([a-fA-F0-9]{32})\|/", re.I)


class Fake115:
    def __init__(self) -> None:
        self.tasks: dict[str, dict] = {}
        self.dirs: dict[str, dict[str, str]] = {"0": {}}
        self._next_cid = 1000
        self.calls: list[tuple[str, str]] = []
        #: 设为 {"state": False, "code": 40101017} 等，模拟 115 拒绝
        self.error: dict | None = None
        #: 模拟 429 限流
        self.rate_limited = False

    # ------------------------------------------------------------------ 控制面

    def complete(self, info_hash: str) -> None:
        self.tasks[info_hash]["percent"] = 100.0
        self.tasks[info_hash]["status"] = "done"

    def set_percent(self, info_hash: str, percent: float) -> None:
        self.tasks[info_hash]["percent"] = percent

    def fail(self, info_hash: str) -> None:
        self.tasks[info_hash]["status"] = "failed"

    # ------------------------------------------------------------------ 传输

    def handler(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        path = request.url.path
        params = dict(request.url.params)
        form: dict[str, str] = {}
        if request.method == "POST" and request.content:
            parsed = parse_qs(request.content.decode("utf-8", "replace"))
            form = {k: v[0] for k, v in parsed.items()}
        ac = params.get("ac") or form.get("ac", "")

        if host == "115.com" and ac == "space":
            return self._json({"state": True, "data": {"sign": "fake-sign", "time": "1700000000"}})

        if host == "clouddownload.115.com" and path.startswith("/web"):
            self.calls.append((request.method, ac))
            if self.rate_limited:
                return httpx.Response(429, headers={"Retry-After": "30"})
            if self.error is not None:
                return self._json(self.error)
            return self._cloud(ac, form or params)

        if host == "webapi.115.com" and path == "/files":
            cid = str(params.get("cid", "0"))
            items = [
                {"cid": child_cid, "n": name, "pid": cid}
                for name, child_cid in self.dirs.get(cid, {}).items()
            ]
            return self._json({"state": True, "data": items})

        if host == "webapi.115.com" and path == "/files/add":
            pid = form.get("pid", "0")
            name = form.get("cname", "")
            cid = str(self._next_cid)
            self._next_cid += 1
            self.dirs.setdefault(pid, {})[name] = cid
            self.dirs.setdefault(cid, {})
            return self._json({"state": True, "data": {"cid": cid}})

        return self._json({"state": False, "code": 404, "message": f"未实现的端点 {host}{path}"}, status=404)

    # ------------------------------------------------------------------ 云下载端点

    def _cloud(self, ac: str, data: dict) -> httpx.Response:
        if ac == "add_task_urls":
            urls = [value for key, value in data.items() if key.startswith("url[") or key == "url"]
            created = []
            for url in urls:
                task = self._task_from_url(url)
                if task is not None:
                    created.append(task["info_hash"])
            return self._json({"state": True, "data": {"info_hash": ",".join(created)}})

        if ac == "add_task_bt":
            info_hash = (data.get("info_hash") or "").lower()
            if info_hash and info_hash not in self.tasks:
                self.tasks[info_hash] = {
                    "info_hash": info_hash,
                    "name": f"bt-{info_hash[:8]}",
                    "size": 1024,
                    "percent": 0.0,
                    "status": "downloading",
                    "files": [{"name": "video.mkv", "size": 1024}],
                }
            return self._json({"state": True, "data": {"info_hash": info_hash}})

        if ac == "get_user_task":
            info_hash = (data.get("info_hash") or "").lower()
            task = self.tasks.get(info_hash)
            return self._json({"state": True, "data": task or {}})

        if ac == "get_task_list":
            tasks = [dict(task) for task in self.tasks.values()]
            return self._json(
                {
                    "state": True,
                    "data": {"tasks": tasks, "count": len(tasks), "page": 1, "page_count": 1},
                }
            )

        if ac == "task_del":
            info_hash = (data.get("info_hash[0]") or data.get("info_hash") or "").lower()
            self.tasks.pop(info_hash, None)
            return self._json({"state": True})

        if ac in {"task_pause", "task_resume", "task_restart"}:
            info_hash = (data.get("info_hash[0]") or "").lower()
            if info_hash in self.tasks:
                self.tasks[info_hash]["status"] = "paused" if ac == "task_pause" else "downloading"
            return self._json({"state": True})

        if ac == "get_quota_info":
            return self._json({"state": True, "data": {"count": 10, "used": 0}})

        return self._json({"state": False, "code": 404, "message": f"未实现的 action {ac}"}, status=404)

    def _task_from_url(self, url: str) -> dict | None:
        magnet = MAGNET.search(url or "")
        if magnet:
            info_hash = magnet.group(1).lower()
            name = "magnet-task"
            dn = re.search(r"[?&]dn=([^&]+)", url)
            if dn:
                name = dn.group(1)
            return self._create_task(info_hash, name)
        ed2k = ED2K.search(url or "")
        if ed2k:
            return self._create_task(ed2k.group(3).lower(), ed2k.group(1))
        return None

    def _create_task(self, info_hash: str, name: str) -> dict:
        if info_hash not in self.tasks:
            self.tasks[info_hash] = {
                "info_hash": info_hash,
                "name": name,
                "size": 2048,
                "percent": 0.0,
                "status": "downloading",
                "files": [{"name": f"{name}.mkv", "size": 2048}],
            }
        return self.tasks[info_hash]

    @staticmethod
    def _json(payload: dict, status: int = 200) -> httpx.Response:
        return httpx.Response(status, content=json.dumps(payload).encode(), headers={"content-type": "application/json"})
