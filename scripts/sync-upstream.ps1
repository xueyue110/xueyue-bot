#Requires -Version 5.1
<#
.SYNOPSIS
  跟进 MovieClaw 上游更新：检查最新版本 → 更新 compose/.env 的 MOVIECLAW_TAG → 拉取镜像重建。

.DESCRIPTION
  只动镜像版本与容器，不动 ./data，也不改本仓库任何代码，所以不会和上游产生冲突。
  -Check 只报告，不拉取、不重建。
  GitHub API 限流时自动改用 git ls-remote 取 tag；有 GITHUB_TOKEN 环境变量则用它提高限额。

.EXAMPLE
  .\scripts\sync-upstream.ps1 -Check
  .\scripts\sync-upstream.ps1
  $env:GITHUB_TOKEN='ghp_xxx'; .\scripts\sync-upstream.ps1
#>
[CmdletBinding()]
param(
  [switch]$Check,
  [switch]$Force,
  [switch]$NoRestart
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$EnvFile  = Join-Path $RepoRoot 'compose/.env'
$ExampleFile = Join-Path $RepoRoot 'compose/.env.example'
$LogFile  = Join-Path $RepoRoot 'docs/UPSTREAM-LOG.md'

function Write-Step([string]$Msg) { Write-Host "==> $Msg" -ForegroundColor Cyan }

function Get-LatestRelease {
  $headers = @{ 'User-Agent' = 'xueyue-bot-sync'; 'Accept' = 'application/vnd.github+json' }
  if ($env:GITHUB_TOKEN) { $headers['Authorization'] = "Bearer $($env:GITHUB_TOKEN)" }
  try {
    $r = Invoke-RestMethod -Uri 'https://api.github.com/repos/movieclaw/movieclaw/releases/latest' -Headers $headers -TimeoutSec 25
    $notes = ($r.body -split "`n" | Where-Object { $_.Trim() } | Select-Object -First 6) -join ' / '
    return [pscustomobject]@{ Tag = $r.tag_name; Notes = $notes; At = $r.published_at }
  } catch {
    Write-Warning "GitHub API 不可用（$($_.Exception.Message)）；改用 git ls-remote 取最新 tag。"
  }
  $out = git ls-remote --tags --refs https://github.com/movieclaw/movieclaw.git 2>$null
  if ($LASTEXITCODE -ne 0 -or -not $out) {
    Write-Warning 'GitHub API 与 git 都不可达；改从 Docker Hub 镜像 tag 取最新版本。'
    try {
      $page = Invoke-RestMethod -Uri 'https://hub.docker.com/v2/repositories/movieclaw/movieclaw/tags?page_size=50&ordering=last_updated' -Headers $headers -TimeoutSec 25
      $tags = $page.results | ForEach-Object { $_.name } | Where-Object { $_ -match '^v?\d+\.\d+\.\d+$' }
      if (-not $tags) { throw 'Docker Hub 上没有找到语义化版本 tag' }
      $latest = $tags | Sort-Object { [version]($_ -replace '^v', '') } | Select-Object -Last 1
      return [pscustomobject]@{ Tag = $latest; Notes = '（来自 Docker Hub tag，GitHub 暂不可达）'; At = $null }
    } catch {
      throw '取不到上游版本：GitHub API / git / Docker Hub 都失败了。检查网络或配置代理后重试。'
    }
  }
  $tags = $out | ForEach-Object { ($_ -split "`t")[1] -replace '^refs/tags/', '' } |
          Where-Object { $_ -match '^v?\d+\.\d+\.\d+$' }
  if (-not $tags) { throw '上游没有找到语义化版本 tag。' }
  $latest = $tags | Sort-Object { [version]($_ -replace '^v', '') } | Select-Object -Last 1
  return [pscustomobject]@{ Tag = $latest; Notes = '（来自 git tag，无 Release 说明）'; At = $null }
}

# ---------- 1. 当前固定版本 ----------
$envText = ''
if (Test-Path $EnvFile) { $envText = Get-Content $EnvFile -Raw -Encoding UTF8 }
elseif (Test-Path $ExampleFile) { $envText = Get-Content $ExampleFile -Raw -Encoding UTF8 }
$current = 'latest'
if ($envText -match '(?m)^MOVIECLAW_TAG=(.+)$') { $current = $Matches[1].Trim() }
Write-Step "当前 MOVIECLAW_TAG: $current"

# ---------- 2. 上游最新版本 ----------
Write-Step '查询 movieclaw/movieclaw 最新版本...'
$release = Get-LatestRelease
$tag = $release.Tag
Write-Step "上游最新: $tag  $(if ($release.At) { "($($release.At))" } else { '' })"

if ($current -eq $tag -and -not $Force) {
  Write-Host '已是最新版本，无需更新。' -ForegroundColor Green
  if (-not $Check) { Write-Host '如需强制重拉镜像：.\scripts\sync-upstream.ps1 -Force' }
  return
}

# ---------- 3. 确认 Docker Hub 有该 tag ----------
Write-Step "确认 Docker Hub 上存在 movieclaw/movieclaw:$tag ..."
try {
  $null = Invoke-RestMethod -Uri "https://hub.docker.com/v2/repositories/movieclaw/movieclaw/tags/$tag" `
          -Headers @{ 'User-Agent' = 'xueyue-bot-sync' } -TimeoutSec 25
  Write-Host '镜像 tag 存在。'
} catch {
  Write-Warning "Docker Hub 上找不到该 tag（Release 的镜像可能还在构建），本次跳过，稍后重试。"
  return
}

if ($Check) {
  Write-Host "发现新版本 $tag（当前 $current）。去掉 -Check 即可升级。" -ForegroundColor Yellow
  return
}

# ---------- 4. 写入 .env ----------
if (-not (Test-Path $EnvFile)) { Copy-Item (Join-Path $RepoRoot 'compose/.env.example') $EnvFile; $envText = Get-Content $EnvFile -Raw -Encoding UTF8 }
if ($envText -match '(?m)^MOVIECLAW_TAG=.+$') {
  $newText = $envText -replace '(?m)^MOVIECLAW_TAG=.+$', "MOVIECLAW_TAG=$tag"
} else {
  $newText = $envText.TrimEnd() + "`nMOVIECLAW_TAG=$tag`n"
}
Set-Content -Path $EnvFile -Value $newText -NoNewline -Encoding UTF8
Write-Step "已写入 MOVIECLAW_TAG=$tag"

# ---------- 5. 拉取并重建 ----------
Push-Location (Join-Path $RepoRoot 'compose')
try {
  Write-Step 'docker compose pull movieclaw ...'
  docker compose pull movieclaw
  if (-not $NoRestart) {
    Write-Step 'docker compose up -d movieclaw ...'
    docker compose up -d movieclaw
  }
} finally { Pop-Location }

# ---------- 6. 记录 ----------
if (-not (Test-Path $LogFile)) {
  Set-Content -Path $LogFile -Value "# MovieClaw 上游更新记录`n`n" -Encoding UTF8
}
$line = "- $(Get-Date -Format 'yyyy-MM-dd HH:mm')  ``$current`` → ``$tag``  $(if ($release.Notes) { "— $($release.Notes)" })"
Add-Content -Path $LogFile -Value $line -Encoding UTF8
Write-Host "完成：已升级到 $tag，记录写入 docs/UPSTREAM-LOG.md" -ForegroundColor Green
Write-Host '数据在 compose/data，未受影响。建议打开网页确认版本与插件状态。'
