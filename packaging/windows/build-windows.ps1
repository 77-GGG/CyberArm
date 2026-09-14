$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$python=Join-Path $root 'simulator/.venv/Scripts/python.exe'
if(!(Test-Path $python)){throw '缺少 simulator/.venv，请先创建项目 Python 环境。'}
Push-Location (Join-Path $root 'simulator/frontend'); try { npm run build } finally { Pop-Location }
& $python -m pip install pyinstaller
$backend=Join-Path $root 'packaging/windows/backend'; $env:PYTHONPATH=Join-Path $root 'simulator/backend'
& $python -m PyInstaller --noconfirm --clean --onedir --name cyberarm-backend --distpath (Join-Path $backend 'dist') --workpath (Join-Path $backend 'build') --specpath $backend --paths (Join-Path $root 'simulator/backend') (Join-Path $backend 'entry.py')
$built=Join-Path $backend 'dist/cyberarm-backend/cyberarm-backend.exe'; Copy-Item $built (Join-Path $backend 'dist/cyberarm-backend.exe') -Force
Push-Location (Join-Path $root 'packaging/windows'); try { if(!(Test-Path 'node_modules')){npm install}; npm run build } finally { Pop-Location }
Write-Host 'Windows 安装包已生成：packaging/windows/dist/'
