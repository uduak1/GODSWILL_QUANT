# GODSWILL — Institutional Multi-Strategy Quantitative Trading Platform

**Status:** Phase 1 complete (architecture + environment). Strategies not yet implemented.

## Requirements
- Windows 10/11
- Python 3.11 or 3.12
- MetaTrader 5 terminal (required from Phase 2 onward)
- VS Code (recommended)

## Install
```powershell
cd C:\path\to\GODSWILL_QUANT
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .