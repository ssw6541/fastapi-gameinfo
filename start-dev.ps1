# Starts backend (8000) and frontend (5173) in separate windows. Run from project root.
$root = $PSScriptRoot
if (-not (Test-Path "$root\backend\.venv")) {
  python -m venv "$root\backend\.venv"
  & "$root\backend\.venv\Scripts\python" -m pip install -r "$root\backend\requirements-dev.txt"
}
if (-not (Test-Path "$root\backend\.env")) { Copy-Item "$root\backend\.env.example" "$root\backend\.env" }
if (-not (Test-Path "$root\frontend\node_modules")) { Push-Location "$root\frontend"; npm install; Pop-Location }
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$root\backend'; .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$root\frontend'; npm run dev"
Write-Host "Frontend: http://localhost:5173   API docs: http://localhost:8000/docs"
