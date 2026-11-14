# plugins/

本目录放自研插件（与官方 movieclaw-plugins 分开维护，避免上游更新冲突）。

## p115-download（进行中）

**目标**：给 MovieClaw 注册一个下载器类型 `p115`，让订阅命中后把磁力/ed2k
直接投给 115 云下载（离线），完成后文件出现在 115 网盘，由 p115-library
生成 STRM 给 Emby —— 即 mediary+flowlink 的「订阅 → 115 → STRM」自动链路，
同时保留 qBittorrent 走 PT。

**已定的设计**

- 实现 `movieclaw_sdk.downloaders.BaseDownloader`，进程外运行（runtime = process）
- 登录：插件自带扫码页（Cookie 存插件数据）
- `submit(magnet|ed2k)` → `POST https://clouddownload.115.com/web/?ac=add_task_urls`
- `submit(torrent_bytes)` → 算 info_hash → `ac=add_task_bt`（115 能认的公开种；PT 私有种秒传不了，提示交给 qBittorrent）
- `get_torrent` → `ac=get_user_task` + 任务列表，映射 progress/状态/文件
- `set_location`/选择性下载：115 离线不支持，明确报 `DownloaderNotSupportedError`
- 保存目录：本地路径前缀 ↔ 115 目录 cid 的映射表（插件设置里配）

**状态**：脚手架与测试进行中，未在真账号验证；先别给生产环境用。

**为什么需要它**：官方 `p115-import` 只支持手动粘链接；`p115-library` 只做
STRM 同步。订阅自动投 115 这一段官方没有现成实现。
