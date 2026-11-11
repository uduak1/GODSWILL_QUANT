# Quick pre-flight: run inside PowerShell at project root.
Write-Host "GODSWILL environment check" -ForegroundColor Cyan
python --version
python -m pip --version
python main.py doctor