# 同事部署手册（MovieClaw + 115 + PT + Emby）

照着做，约 30 分钟。前提：一台能跑 Docker 的 NAS / 迷你主机，115 会员账号（离线下载要用配额），PT 站账号（可选）。

---

## 0. 目录规划（先想清楚，后面不改）

| 宿主机目录 | 容器内 | 放什么 |
|---|---|---|
| `./data` | `/app/data` | MovieClaw 全部数据（备份这一个就够） |
| `./media` | `/media` | 本地媒体库 + `strm/` 子目录 |
| `./downloads` | `/downloads` | qBittorrent 下载中/做种目录 |

`media` 下面建议：

```text
media/
├── movies/           # PT 入库的电影（MovieClaw 本地库1）
├── tv/               # PT 入库的剧集（MovieClaw 本地库2）
└── strm/             # p115-library 生成的 .strm（Emby 读这里）
    ├── 电影/
    └── 剧集/
```

---

## 1. 起服务

```bash
cd compose
cp .env.example .env
```

改 `.env`：

```ini
MEDIA_DIR=/volume1/media      # 换成 NAS 实际路径
DOWNLOAD_DIR=/volume1/downloads
TZ=Asia/Shanghai
```

```bash
docker compose --profile emby up -d
docker compose ps
```

打开 `http://<NAS>:3000`，创建管理员账号。

---

## 2. 装插件

MovieClaw 网页 → **设置 → 插件 → 插件市场**，依次安装并**批准权限**：

1. `p115-import`（115 分享/离线链接转存）
2. `p115-library`（115 → STRM）
3. `cloud-115`（115 存储后端，秒传/直链）
4. `qbittorrent-downloader` 已随主程序自带，无需安装

> 插件市场索引默认指向 movieclaw-plugins 的 catalog Release，连不上时检查 NAS 出网（GitHub / ghcr）。

---

## 3. 接 qBittorrent（PT 下载）

1. 浏览器打开 `http://<NAS>:8080`，默认账号 `admin`，初始密码看容器日志：
   `docker logs qbittorrent 2>&1 | grep -i password`
2. 改密码后：**设置 → Web UI**，确认端口 8080、关闭「仅本机访问」
3. MovieClaw → **设置 → 下载器 → 添加**：
   - 类型：qBittorrent
   - 地址：`http://qbittorrent:8080`（MovieClaw 容器内访问，别写宿主机 IP）
   - 用户名/密码：刚才设的
   - 保存目录建议映射到 `/downloads`（MovieClaw 里的路径）
4. 点「测试连接」通过即可。订阅/手动下载都会投给它。

---

## 4. 登录 115（扫码）

**选一个别的工具没在用的登录端**（默认推荐「支付宝小程序」）。115 同一端同时只能在线一个：
网页端会和浏览器互踢，CloudDrive2 / 其他工具用过的端也会互踢。

- p115-import 与 cloud-115 各自扫码一次（两个插件独立会话），都选同一个端也行，但别和别的软件撞。

---

## 5. 建媒体库

MovieClaw → **媒体库 → 新建**：

| 库 | 类型 | 路径 | 说明 |
|---|---|---|---|
| 电影 | 电影 | `/media/movies` | PT 下载入库的落点 |
| 剧集 | 剧集 | `/media/tv` | 同上 |
| 115-STRM（可选） | 电影/剧集 | `/media/strm/电影`、`/media/strm/剧集` | 让 MovieClaw 也能直接播 115 的片 |

若只用 Emby 看 115，这一步的 STRM 库可以让 Emby 去读，MovieClaw 只留本地库也行。

---

## 6. 配置 STRM 生成（p115-library）

侧边栏 **「115网盘」→ 核心配置**：

1. 115 账号：已扫码
2. **115 媒体库 cid**：点「点击输入」选 115 上放电影的目录（如 `/影视/电影`）
3. **本地 STRM 目录**：填容器内路径 `/media/strm/电影`（必须先有第 5 步的库指向它，否则写入被拒）
4. 保存配置 → **数据同步 → 全量同步**

完成后 `.strm` 会写到 `/media/strm/电影`。剧集重复一遍（多目录映射）。

之后 115 里有变动（转存、上传），p115-library 会**增量同步**并自动通知 MovieClaw 扫库。

---

## 7. 直接加 115 链接

侧边栏 **「115 转存」**：

- 粘贴 **115 分享链接**（带提取码：`https://115.com/s/xxxx?password=abcd` 或 `xxxx-abcd`）
- 粘贴 **磁力 / ed2k**（走 115 离线下载，消耗会员离线配额）
- 可一次贴多条；提交后在「看板」看进度
- 完成后自动识别、分库、命名、核验入库；需要通知就勾选「完成通知」

---

## 8. Emby 接 STRM

Emby → 添加媒体库 → 路径选 `/media/strm/电影`、`/media/strm/剧集`。
播放时 Emby 请求 `.strm`，由 MovieClaw/115 直链 302 播放，不落本地盘。

> 注意：Emby 容器必须挂载同一个 `/media`（compose 里已挂）。

---

## 9. 混合来源怎么配

- **PT 资源**：订阅/手动下载 → qBittorrent → `/downloads` → MovieClaw 监听导入 → `/media/movies`、`/media/tv`
- **115 资源**：115 转存页提交 → 115 网盘 → p115-library 生成 STRM → Emby / MovieClaw STRM 库
- 两套库互不干扰；同一部片两边都有时，MovieClaw 会按各自的库分别入账

---

## 10. 日常维护

```bash
docker compose ps                 # 状态
docker compose logs -f movieclaw  # 日志
docker compose pull && docker compose up -d   # 升级（或直接用 scripts/sync-upstream.ps1）
```

- 备份 `./data`（含隐藏文件 `.secret_key`）
- 升级 MovieClaw：`scripts/sync-upstream.ps1`
- 115 风控：p115-library 撞到 405 会自动等冷却重扫；别频繁全量同步
- 种子做种：qBittorrent 保持运行，MovieClaw 删种前会先确认
