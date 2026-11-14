#Requires -Version 5.1
<#
.SYNOPSIS
  把 plugins/p115-download 打包成 MovieClaw 插件包（.mcplugin）。

.EXAMPLE
  .\scripts\build-plugin.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PluginDir = Join-Path $RepoRoot 'plugins/p115-download'
$Toml = Join-Path $PluginDir 'movieclaw-plugin.toml'
$Dist = Join-Path $PluginDir 'dist'

if (-not (Test-Path $Toml)) { throw "找不到插件清单：$Toml" }
$version = (Select-String -Path $Toml -Pattern '^version\s*=\s*"(.+)"').Matches[0].Groups[1].Value
$name = (Select-String -Path $Toml -Pattern '^id\s*=\s*"(.+)"').Matches[0].Groups[1].Value

New-Item -ItemType Directory -Force $Dist | Out-Null
$out = Join-Path $Dist "$name-$version.mcplugin"
if (Test-Path $out) { Remove-Item $out -Force }

# 插件包根目录放 movieclaw-plugin.toml、代码目录与 README；不带 tests/dist/缓存
$stage = Join-Path $env:TEMP "mcpkg-$name-$version"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item (Join-Path $PluginDir 'movieclaw-plugin.toml') $stage
Copy-Item (Join-Path $PluginDir 'README.md') $stage
Copy-Item (Join-Path $PluginDir 'p115_download') $stage -Recurse
Get-ChildItem $stage -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
$tmp = Join-Path $env:TEMP "$name-$version.zip"
if (Test-Path $tmp) { Remove-Item $tmp -Force }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $tmp -CompressionLevel Optimal
Move-Item $tmp $out -Force
Remove-Item $stage -Recurse -Force

Write-Host "已生成：$out" -ForegroundColor Green
Write-Host "在 MovieClaw → 设置 → 插件 → 手动上传该文件即可。"
