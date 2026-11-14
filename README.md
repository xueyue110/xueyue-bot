# movieclaw-kit

基于 [MovieClaw](https://github.com/movieclaw/movieclaw) 的一体化影音方案，目标是复刻
「mediary + flowlink + Emby」那套玩法：

- **PT 资源** → qBittorrent 下载到本地盘 → MovieClaw 自动识别、整理、入库
- **115 分享链接 / 离线链接（磁力、ed2k）** → 在 MovieClaw 网页里直接粘贴提交 → 转存进 115
- **115 片源** → 自动生成 `.strm` → Emby 像看本地片一样播放（302 直链）
- 订阅、洗版、刮削、海报墙、多成员权限、AI 助手，全部用 MovieClaw 自带能力

本仓库不复制 MovieClaw 源码，只做「部署编排 + 官方插件选型 + 更新同步」，
所以上游更新不会和我们的改动冲突。

## 目录

```text
compose/    docker-compose.yml + .env.example   —— 一条命令起 MovieClaw / qBittorrent / Emby(可选)
docs/       SETUP.zh-CN.md（同事照着做）· ARCHITECTURE.md（链路图）
scripts/    sync-upstream.ps1（跟进 MovieClaw 新版本）· status.ps1
plugins/    自研插件（进行中，见 plugins/README.md）
data/       运行时数据（git 忽略，备份它即可）
```

## 快速开始

```bash
cd compose
cp .env.example .env        # 改 TZ / MEDIA_DIR / DOWNLOAD_DIR / 端口
docker compose --profile emby up -d
```

打开 `http://<NAS 地址>:3000` 建管理员账号，然后按 [`docs/SETUP.zh-CN.md`](docs/SETUP.zh-CN.md)
安装插件、建库、登录 115、挂 Emby。

## 跟进 MovieClaw 更新

```powershell
.\scripts\sync-upstream.ps1            # 检查 → 更新镜像 tag → 拉取重建
.\scripts\sync-upstream.ps1 -Check     # 只看有没有新版本，不动容器
```

脚本查 GitHub Releases，把最新版本写进 `compose/.env` 的 `MOVIECLAW_TAG`，
再 `docker compose pull && up -d`；升级记录追加到 `docs/UPSTREAM-LOG.md`。
数据都在 `./data`，升级不动数据。

## 用到的 MovieClaw 插件（官方仓库 movieclaw-plugins）

| 插件 | 作用 |
|---|---|
| `p115-import` | 115 分享链接 / ed2k / 磁力 → 转存入库，自带提交页与看板 |
| `p115-library` | 115 目录 → STRM（增量同步、剧集直链预取、NFO/图片/字幕跟随） |
| `cloud-115` | 115 作为存储后端：扫码登录、秒传、直链、回收站 |
| `qbittorrent-downloader` | PT 下载（主程序随带） |
| **`p115-download`（本仓库自研）** | 下载器类型 `p115`：订阅命中后磁力/ed2k 直接投 115 云下载，PT 继续走 qBittorrent；见 [plugins/p115-download](plugins/p115-download) |

## 许可

本仓库脚本与文档以 MIT 发布；MovieClaw 本体见其仓库许可（LICENSE）。
