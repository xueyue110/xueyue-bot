# 用自己仓库的 Actions 构建镜像

默认 `compose/.env` 用的是官方镜像 `movieclaw/movieclaw`。想用**自己仓库构建的镜像**
（镜像来源可控、可复现），用仓库里的 `build-image` 工作流。

## 一、构建

1. GitHub → 你的仓库 → **Actions** → 左侧 **build-image** → **Run workflow**
2. `ref` 填上游 MovieClaw 的 tag，例如 `v0.50.0`（和 `compose/.env` 的 `MOVIECLAW_TAG` 保持一致）
3. 等待完成（首次约 15–30 分钟；arm64 走 QEMU 会更慢）

产物：`ghcr.io/xueyue110/movieclaw:v0.50.0`（amd64 + arm64 双架构）。

## 二、让 GHCR 镜像可被拉取

GHCR 的包默认是 **private**：

- 私有：NAS 上先 `docker login ghcr.io -u xueyue110`，密码用 GitHub 的 PAT（`read:packages`）
- 公开：GitHub → 你的仓库 → Packages → 找到 `movieclaw` → Package settings → Change visibility → Public

## 三、切换到自己的镜像

`compose/.env`：

```ini
MOVIECLAW_IMAGE=ghcr.io/xueyue110/movieclaw
MOVIECLAW_TAG=v0.50.0
```

然后：

```bash
cd compose
docker compose pull movieclaw && docker compose up -d movieclaw
```

## 四、和上游同步

`scripts/sync-upstream.ps1` 只改 `MOVIECLAW_TAG`，不会自动帮你构建新镜像。
用 ghcr 镜像时，升级流程是：

1. `sync-upstream.ps1 -Check` 看有没有新版本
2. 有新版本 → Actions 里用新 tag 跑一次 `build-image`
3. 镜像出来后，`sync-upstream.ps1` 更新 tag 并重建

## 注意事项

- 镜像从**上游源码**构建，不是我们改过的代码；构建的可复现性由 `ref`（tag）保证。
- 上游 `Dockerfile` 若调整（构建参数、基础镜像），工作流不需要改；如果构建失败，看 Actions 日志里
  Dockerfile 那一步，把报错发我。
- 想校验镜像来源：`docker image inspect ghcr.io/xueyue110/movieclaw:v0.50.0` 看 `org.opencontainers.image.*` 标签。
