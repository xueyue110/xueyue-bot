# plugins/

本目录放自研插件（与官方 movieclaw-plugins 分开维护，避免上游更新冲突）。

## p115-download v0.1.0

**目标**：给 MovieClaw 注册一个下载器类型 `p115`，让订阅命中后把磁力/ed2k
直接投给 115 云下载（离线），完成后文件出现在 115 网盘，由 p115-library
生成 STRM 给 Emby —— 即 mediary+flowlink 的「订阅 → 115 → STRM」自动链路，
同时保留 qBittorrent 走 PT。

**实现**

- 实现 `movieclaw_sdk.downloaders.BaseDownloader`，进程外运行，类型 `p115`
- 登录：下载器配置的「密码」栏填 115 Cookie（`UID=…; CID=…; SEID=…; KID=…`）
- `submit(magnet/ed2k)` → `clouddownload.115.com/web/?ac=add_task_urls`
- `submit(torrent_bytes)` → 本地算 info_hash → `ac=add_task_bt`（私有站取不到 peer 会失败，PT 请走 qBittorrent）
- `get_torrent` / `list_torrents` → 115 任务查询，映射进度、状态、文件清单
- 保存目录约定：本地 `/media/115/**` ↔ 115 网盘同名路径，缺目录自动创建
- `set_location` / 选择性下载：115 离线不支持，明确报 `DownloaderNotSupportedError`
- 115 限流/失效/网络错误分别映射成 MovieClaw 的 `DownloaderConnectError` / `DownloaderAuthError`

**测试**：`plugins/p115-download/tests`，19 个用例全绿，用 `httpx.MockTransport`
模拟 115（`tests/fake115.py`），不连网、不用账号。覆盖 Cookie 缺失/失效、限流、
磁力/ed2k/种子提交、目录映射与建目录、进度与完成、列表、删除幂等、不支持操作。

**打包/安装**：`scripts/build-plugin.ps1` → `plugins/p115-download/dist/p115-download-0.1.0.mcplugin`，
在 MovieClaw → 设置 → 插件 → 手动上传。

**已知边界**

- 未在真实 115 账号上联调（当前环境无账号）。接口路径取自 p115client（MIT），
  网页接口可能要求 sign/time，客户端按需补充；真实账号首次使用请先做一次
  「加任务 → 完成 → STRM 出现」的全流程验证。
- 不处理 115 分享链接（分享转存由官方 `p115-import` 插件的页面负责）。
- 115 云下载没有全局限速/队列，相关接口静默忽略。
