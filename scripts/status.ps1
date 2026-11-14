#Requires -Version 5.1
<#
.SYNOPSIS
  movieclaw-kit 状态速查：容器状态、当前固定版本、健康检查、115/Emby 端口。

.EXAMPLE
  .\scripts\status.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ComposeDir = Join-Path $RepoRoot 'compose'
$EnvFile = Join-Path $ComposeDir '.env'

Write-Host '=== 版本 ===' -ForegroundColor Cyan
if (Test-Path $EnvFile) {
  Select-String -Path $EnvFile -Pattern '^(MOVIECLAW_TAG|MC_PORT|QB_PORT|EMBY_PORT|MEDIA_DIR|DOWNLOAD_DIR)=' |
    ForEach-Object { $_.Line }
} else {
  Write-Warning '.env 不存在，先 cp compose/.env.example compose/.env'
}

Write-Host "`n=== 容器 ===" -ForegroundColor Cyan
Push-Location $ComposeDir
try {
  if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose ps
    Write-Host "`n=== MovieClaw 健康 ===" -ForegroundColor Cyan
    docker inspect --format '{{.Name}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}} status={{.State.Status}}' movieclaw 2>$null
  } else {
    Write-Warning '未找到 docker 命令（在 NAS 上执行本脚本）'
  }
} finally { Pop-Location }
