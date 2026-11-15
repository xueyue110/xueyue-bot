# 同事部署手册（MovieClaw + 115 + PT + Emby）

照着做，约 30 分钟。前提：一台能跑 Docker 的 NAS / 迷你主机，115 会员账号（离线下载要用配额），PT 站账号（可选）。

> **默认玩法见 [`ROUTE-115.zh-CN.md`](ROUTE-115.zh-CN.md)**：PT 订阅 → 本地硬链刮削 → 上传 115 库 → STRM → Emby。
> 本手册第 5、6 步是它的精简版；7.5 / 7.6 是可选增强（订阅投 115、待刮削目录）。

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

## 7.5 可选：订阅自动投 115（自研 p115-download，主路线用不到）

> 主路线（ROUTE-115）是「本地硬链 + 刮削 → 上传 115 库」，官方插件已经覆盖，**不需要本节**。
> 只有当你想让订阅跳过本地、直接把磁力投给 115 时，才装这个插件。

如果你想让**订阅命中后自动把磁力/ed2k 投给 115**（不再手动粘），装本仓库的插件：

1. 打包：Windows 上 `Set-ExecutionPolicy -Scope Process Bypass` 后执行
   `scripts\build-plugin.ps1`，得到 `plugins/p115-download/dist/p115-download-0.2.0.mcplugin`
2. MovieClaw → 设置 → 插件 → **手动上传**该文件 → 批准权限
3. 设置 → 下载器 → 添加：
   - 类型：`115 云下载`
   - 占位地址：`local`
   - 密码：115 Cookie（`UID=…; CID=…; SEID=…; KID=…`）
4. 保存路径用 `/media/115/<网盘目录>`，例如 `/media/115/电影`，插件会把它映射到 115 网盘的 `/电影`
5. 订阅/手动下载时选这个下载器；**PT 种子仍选 qBittorrent**（私有站 115 取不到 peer）

> 该插件逻辑已用假 115 后端测试通过，但**未在真实 115 账号联调**。上线前先手动跑一次
> 「加磁力 → 完成 → STRM 出现」验证；遇到接口变动到 `plugins/p115-download/README.md` 看排查点。

### 7.6 转存即刮削：115 待刮削文件夹

目标：**离线/分享先转存进 115 的「待刮削」目录，文件一进去就自动识别、刮削、进媒体库**。两种接法：

**A. 挂载 + MovieClaw 监听导入（推荐，零新代码）**

1. CloudDrive2 把 115 挂到 NAS（你现有 `emby-115` 那套），compose 里给 MovieClaw 挂同一路径，例如 `/media/115`
2. MovieClaw → 媒体库 → 库设置 → **监听导入**：源目录选 `/media/115/待刮削`，目标选对应库
3. 115 里往 `/待刮削` 转存/上传 → 挂载层出现文件 → 监听导入识别、改名、搬入媒体库
4. p115-library 增量同步 → STRM → Emby

**B. 插件轮询（不挂载，需真账号联调）**

compose 里给 MovieClaw 加环境变量：

```yaml
- P115_WATCH_COOKIE=UID=…; CID=…; SEID=…; KID=…
- P115_WATCH_STAGING=/媒体/待刮削
- P115_WATCH_INTERVAL=300
```

插件每 5 分钟列一次待刮削目录：新条目 → `dl.resolve-target` 识别 → 在媒体库云目录下建条目目录 →
搬过去 → 对该目录触发 `library.scan.start`。认不住的条目**不移动**，只记日志等人工处理。

> B 依赖 MovieClaw 的「网盘库」（库根是 115 上的目录）和插件权限 `dl.resolve-target`/`library.scan.start`；
> 效果与 A 相同，但少了挂载这一层，适合没有 CloudDrive2 的机器。

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
