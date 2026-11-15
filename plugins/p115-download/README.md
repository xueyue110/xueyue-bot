# p115-download · 115 云下载下载器

给 MovieClaw 注册下载器类型 `p115`：订阅或手动下载投递的**磁力 / ed2k** 直接进 115 云下载（离线），
完成后文件落在 115 网盘目录，再由官方 `p115-library` 插件同步成 `.strm` 给 Emby。
PT 资源继续用 qBittorrent，两种下载器可以同时存在，按订阅/下载时的目标选择。

> 状态：**v0.1.0，逻辑已用假 115 后端测过，未在真实账号上验证**。生产使用前请在测试号上跑一遍加任务 → 完成 → STRM。

## 安装

1. 打包：`scripts/build-plugin.ps1` → 生成 `plugins/p115-download/dist/p115-download-0.1.0.mcplugin`
2. MovieClaw → 设置 → 插件 → 手动上传 `.mcplugin` → 批准权限
3. 设置 → 下载器 → 添加：
   - 类型：`115 云下载`
   - 占位地址：`local`（随意，115 不用地址）
   - 密码：填 115 网页 Cookie，形如 `UID=…; CID=…; SEID=…; KID=…`
4. 点「测试连接」，通过即生效

## 目录约定

下载器的保存路径统一以 **`/media/115`** 开头，映射到 115 网盘的同名相对路径：

```text
保存路径 /media/115/电影/新片
        → 115 网盘 /电影/新片（不存在就逐级创建）
```

不在该前缀下的保存路径会交给 115 默认云下载目录（落点以 115 为准）。
所以推荐在 MovieClaw 里把「115 库」的根目录设为 `/media/115`，或者手动下载时把保存路径填成这个前缀。

## 能力与限制

| 能力 | 说明 |
|---|---|
| 提交磁力 | `add_task_urls`，info_hash 取自 `xt=urn:btih:` |
| 提交 ed2k | 用 ed2k 文件哈希（MD4）当任务标识 |
| 提交 .torrent（PT 种子） | 算 info_hash 走 `add_task_bt`；**私有站的种 115 取不到 peer，会失败**，这类请用 qBittorrent |
| 进度 / 文件清单 | 查 `get_user_task` / `get_task_list` |
| 暂停 / 继续 / 删除 | 对应 115 任务操作，删除可选删源文件 |
| 改保存目录 | 不支持（115 离线不支持事后搬移），提前把目标目录映射到 `/media/115` |
| 选择性下载 | 不支持 |
| 限速 / 队列 | 115 云下载没有对应设置，接口静默忽略 |

## 完成之后

文件在 115 网盘出现后，由 `p115-library` 的增量同步发现（115 操作动态触发），
在本地 STRM 目录写出 `.strm` 并通知 MovieClaw 扫库：订阅按「库里有」关单，
Emby 直接读 STRM 播放（302 直链，不落本地盘）。

## 待刮削目录自动整理（v0.2.0）

除了下载器，插件还带一个「转存即刮削」循环：115 里指定一个待刮削目录，任何手段
（离线、分享转存、手动上传）放进去的新条目，会被自动识别、移入媒体库目录并触发扫描。

配置（MovieClaw 容器的环境变量）：

```yaml
environment:
  - P115_WATCH_COOKIE=UID=…; CID=…; SEID=…; KID=…   # 115 Cookie
  - P115_WATCH_STAGING=/媒体/待刮削                   # 115 网盘里的待刮削目录
  - P115_WATCH_INTERVAL=300                          # 轮询秒数，最小 30
```

流程（每个 tick）：

1. 列待刮削目录，取新条目（目录或单文件）
2. 按名字推断 movie/tv，调宿主 `dl.resolve-target` 识别
3. 认不住（not_found/ambiguous）→ **不移动**，只记日志，等人工处理
4. 认住 → 在媒体库云目录下建条目目录，把条目移进去
5. 对目标目录调 `library.scan.start`（`cloud_paths` 只扫这一处）→ 刮削入账
6. p115-library 增量同步出 STRM

权限（插件清单已声明）：`dl.resolve-target`、`library.scan.start`。

限制：识别后不重命名文件（沿用发布名，识别靠 NER/解析）；已处理条目记在内存，
插件重启后会重扫一遍（条目不在了就自然跳过）；不支持分级/多级子目录混合投放。

## 安全

- Cookie 存在下载器配置的密码字段里，和 qBittorrent 密码同一处，按 MovieClaw 的下载器配置存储；
  不要在日志/截图里外泄。
- 建议单独用一个登录端（例如支付宝小程序）扫码拿 Cookie，避免和 CloudDrive2 / 浏览器互踢。
- 删除任务可以删 115 里的源文件；MovieClaw 的删除确认流程会先要求确认。

## 测试

```bash
python -m pytest tests -q
```

测试用 `httpx.MockTransport` 模拟 115（`tests/fake115.py`），不连网、不用账号。
覆盖：Cookie 缺失/失效、限流、磁力/ed2k/种子提交、目录映射与自动建目录、
进度与完成态、列表、删除、幂等、不支持的操作。
