# 架构：三种来源、两条链路

```text
                 ┌──────────────────────────── MovieClaw ────────────────────────────┐
                 │                                                                   │
 PT 站(索引器) ──┤ 订阅/手动搜索                                                     │
                 │        │                                                          │
                 │        ▼                                                          │
                 │   qBittorrent ──► /downloads ──► 监听导入(识别/改名) ──► /media/movies│
                 │                                                   /media/tv        │
                 │                                                                   │
 115 分享/磁力 ──┤ 「115 转存」页 ──► 115 网盘 ──► p115-library ──► /media/strm/*.strm │
                 │                          ▲                                        │
                 │                 cloud-115(登录/秒传/直链)                          │
                 └───────────────────────────────────────────────────────────────────┘
                                                   │
                                                   ▼
                                    Emby 读 /media/strm（302 直链播放）
```

## 两条链路各自负责什么

| 链路 | 由谁搬运 | 落点 | 播放 |
|---|---|---|---|
| PT | qBittorrent（本地盘） | `/media/movies`、`/media/tv` | MovieClaw / Emby 直接读文件 |
| 115 | p115-import 转存到网盘 | 115 网盘目录 | MovieClaw 302 直链；Emby 读 p115-library 生成的 `.strm` |

## 为什么不复制 MovieClaw 源码

- 上游每天在动，复制源码就要长期 rebase；
- 所有扩展都走**官方插件契约**（下载器适配器、通道、库扫描），插件包独立升级；
- 本仓库只锁镜像版本 + 部署参数，升级 = 换镜像 tag（`scripts/sync-upstream.ps1`）。

## 自研插件的位置（plugins/）

`plugins/p115-download`：把「订阅 → 115 离线/转存」补成下载器适配器，
让订阅命中后可以直接投给 115，而不是只走 qBittorrent。当前状态见
[`plugins/README.md`](../plugins/README.md)。
