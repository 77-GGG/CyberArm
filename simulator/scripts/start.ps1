param([int]$Port = 8765, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$simulatorRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $simulatorRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw '缺少项目 Python 环境，请先按 simulator/README.md 安装。' }
if (!(Test-Path -LiteralPath (Join-Path $simulatorRoot 'frontend/dist/index.html'))) { throw '请先在 simulator/frontend 运行 npm run build。' }
$env:PYTHONPATH = Join-Path $simulatorRoot 'backend'
$env:PYTHONIOENCODING = 'utf-8'
if (!$NoBrowser) { Start-Process "http://127.0.0.1:$Port" }
& $pythonPath -m uvicorn cyberarm.server:app --host 127.0.0.1 --port $Port
