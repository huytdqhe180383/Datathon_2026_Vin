@echo off
setlocal

set "PORT=%~1"
if "%PORT%"=="" set "PORT=7860"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

set "GRADIO_SERVER_PORT=%PORT%"

rem Starts the UI with: uv run python -m sql_rag_agent.ui
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$port = [int]$env:GRADIO_SERVER_PORT;" ^
  "$repoRoot = '%REPO_ROOT%';" ^
  "$listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "if ($listener) { $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue; if ($process) { Write-Host ('Stopping existing SQL Agent UI on port {0} (PID {1}).' -f $port, $listener.OwningProcess); Stop-Process -Id $listener.OwningProcess -Force; Start-Sleep -Seconds 1 } }" ^
  "$env:PYTHONPATH = Join-Path $repoRoot 'src';" ^
  "$env:GRADIO_SERVER_PORT = [string]$port;" ^
  "$outLog = Join-Path $repoRoot '.tmp_sql_rag_agent_ui.out.log';" ^
  "$errLog = Join-Path $repoRoot '.tmp_sql_rag_agent_ui.err.log';" ^
  "Remove-Item $outLog, $errLog -Force -ErrorAction SilentlyContinue;" ^
  "$process = Start-Process -FilePath 'uv' -ArgumentList 'run','python','-m','sql_rag_agent.ui' -WorkingDirectory $repoRoot -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Minimized -PassThru;" ^
  "Start-Sleep -Seconds 5;" ^
  "$url = ('http://127.0.0.1:{0}' -f $port);" ^
  "Start-Process $url;" ^
  "Write-Host ('Datathon SQL Agent UI started on {0} (PID {1}).' -f $url, $process.Id);"

if errorlevel 1 (
  echo Failed to restart Datathon SQL Agent UI.
  pause
  exit /b 1
)

endlocal
