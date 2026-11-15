# xueyue-bot

基于 [MovieClaw](https://github.com/movieclaw/movieclaw) 的一体化影音方案，复刻
「mediary + flowlink + Emby」那套玩法，全部能力由 MovieClaw 本体 + 官方插件提供，
本仓库不改 MovieClaw 源码：

- **PT 订阅** → qBittorrent 下载 → 本地硬链接 + 刮削 → 上传到 115 库 → 本地释放
- **115 库** → `p115-library` 生成 `.strm` → Emby 刮削播放（302 直链，不落盘）
- **115 分享/离线链接** → 官方 `p115-import` 转存入库（可选，手动加片用）
- 订阅、洗版、刮削、海报墙、多成员权限、AI 助手，全部用 MovieClaw 自带能力

## 主路线

**PT 订阅 → 本地硬链刮削 → 上传 115 库 → 本地释放 → p115-library 生成 STRM → Emby 刮削播放**

这就是 MovieClaw 原生的「115 库」形态（库主根选 115 文件夹），不需要改主程序。
完整配置见 [`docs/ROUTE-115.zh-CN.md`](docs/ROUTE-115.zh-CN.md)。

## 目录

```text
compose/     docker-compose.yml + .env.example   —— 一条命令起 MovieClaw / qBittorrent / Emby(可选)
docs/        ROUTE-115（主路线）· SETUP（同事手册）· ARCHITECTURE（链路）
             BUILD-IMAGE（自己建镜像）· SECURITY（安全检查记录）
scripts/     sync-upstream.ps1（跟进上游版本）· status.ps1
.github/     build-image.yml（用本仓库 Actions 构建并推送镜像到 ghcr.io）
data/        运行时数据（git 忽略，备份它即可）
```

## 快速开始

```bash
cd compose
cp .env.example .env        # 改 TZ / MEDIA_DIR / DOWNLOAD_DIR / 端口
docker compose --profile emby up -d
```

打开 `http://<NAS 地址>:3000` 建管理员账号，然后按 [`docs/SETUP.zh-CN.md`](docs/SETUP.zh-CN.md)
安装插件、建库、登录 115、挂 Emby。

## 用自己仓库的镜像

默认用官方镜像 `movieclaw/movieclaw`。想用**本仓库构建的镜像**：

1. 仓库 Actions 里手动跑一次 **build-image**（输入上游 tag，如 `v0.50.0`）
2. 镜像推到 `ghcr.io/xueyue110/movieclaw:<tag>`
3. `compose/.env` 里改：

```ini
MOVIECLAW_IMAGE=ghcr.io/xueyue110/movieclaw
MOVIECLAW_TAG=v0.50.0
```

细节与注意事项见 [`docs/BUILD-IMAGE.md`](docs/BUILD-IMAGE.md)。

## 跟进 MovieClaw 更新

```powershell
.\scripts\sync-upstream.ps1            # 检查 → 更新镜像 tag → 拉取重建
.\scripts\sync-upstream.ps1 -Check     # 只看有没有新版本，不动容器
```

数据都在 `./data`，升级不动数据；升级记录追加到 `docs/UPSTREAM-LOG.md`。

## 用到的 MovieClaw 插件（官方仓库 movieclaw-plugins）

| 插件 | 作用 |
|---|---|
| `cloud-115` | 115 作为存储后端：新片自动上传、本地自动腾空、秒传、直链、回收站 |
| `p115-library` | 115 目录 → STRM（增量同步、剧集直链预取、NFO/图片/字幕跟随） |
| `p115-import` | 115 分享链接 / ed2k / 磁力 → 转存入库（可选，手动加片） |
| `qbittorrent-downloader` | PT 下载（主程序随带） |

## 安全

仓库内容与镜像来源的检查记录见 [`docs/SECURITY.md`](docs/SECURITY.md)。

## 许可

本仓库脚本与文档以 MIT 发布；MovieClaw 本体见其仓库许可（LICENSE）。
