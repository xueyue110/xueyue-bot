# 安全检查记录

对象：本仓库（xueyue-bot）自带的全部文件。范围是**仓库内容**，不含 MovieClaw 上游源码、
官方插件包与 Docker 镜像内部（这些是外部信任边界，见文末）。

## 一、检查方法（可复现）

```powershell
# 1) 仓库文件清单
git ls-files

# 2) 可疑代码模式：动态执行、命令拼接、下载即执行、反弹 shell
#    eval(/exec(/os.system/subprocess/Invoke-Expression/DownloadString/
#    FromBase64String/nc -e/bash -i//dev/tcp/base64 -d/curl|sh/wget|sh
# 3) 凭据泄漏：私钥头、GitHub token、115 Cookie、OpenAI key
# 4) 出站地址：把文件里出现的所有 http(s) 主机列出来人工过一遍
```

## 二、结果（2026-11-15）

| 项目 | 结果 |
|---|---|
| 文件数 | 11（compose、docs、两个 ps1 脚本、一个 GitHub Actions 工作流） |
| 可疑代码模式 | **0 处**（无 eval/exec、无命令拼接、无下载即执行、无反弹 shell、无 base64 混淆） |
| 凭据泄漏 | **0 处**（无私钥、无 token、无 Cookie、无 API key；`.env` 被 gitignore） |
| 出站地址 | 只有 `api.github.com`（查版本）、`hub.docker.com`（查镜像 tag）、`github.com`（git push、文档链接）；`115.com` 仅出现在文档示例里，不会被程序请求 |
| 工作流权限 | `contents: read` + `packages: write`，只用于构建镜像推 GHCR；无 `pull_request_target`、无 `secrets` 外传 |
| 脚本行为 | `sync-upstream.ps1`：读 `.env` → 查版本 → 改 tag → `docker compose pull/up`；不执行远端脚本、不写系统目录（除自身 `.env`/日志） |

## 三、残留风险（如实说）

1. **镜像来源**：默认用 Docker Hub 官方镜像 `movieclaw/movieclaw` 与 `linuxserver/qbittorrent`、`emby/embyserver`。
   镜像内容无法在本仓库里逐行审计；想收紧就用本仓库 Actions 自己构建（[BUILD-IMAGE](BUILD-IMAGE.md)）。
2. **插件信任**：插件从官方市场安装（索引带签名、包带 sha256），但插件代码本身是第三方作者写的；
   安装前看一眼它申请的权限（操作、网络、目录）。
3. **工作流里的 Actions**：用的是 `actions/checkout@v4` 等主版本标签；要最高确定性可改成钉 commit SHA。
4. **115 凭据**：扫码/Cookie 存在 MovieClaw 的加密配置里，不在本仓库；别把 `.env`、`data/`、截图里的 Cookie 外传。
5. **网络暴露**：`3000` 端口只在内网或走 Tailscale/WireGuard；不要直接映射到公网。

## 四、建议

- 镜像锁定版本（`MOVIECLAW_TAG`），升级前先 `-Check` 看变更；
- 用 ghcr 自建镜像时，拉取后用 `docker image inspect` 看 `org.opencontainers.image.*` 标签确认来源；
- 定期 `docker compose pull` + 备份 `compose/data`（含隐藏文件 `.secret_key`）；
- 插件只从「设置 → 插件 → 插件市场」装，不手动上传来源不明的 `.mcplugin`。
