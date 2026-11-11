"""Broker-agnostic MetaTrader 5 terminal discovery.

Never hardcodes a broker name or install path. Tries, in priority order:

  1. Running terminal64.exe process (via Get-Process on Windows)
  2. MetaQuotes registry records (HKCU, HKLM, HKLM\\WOW6432Node)
  3. Filesystem scan of standard install roots
  4. Returns [] if none found — caller then relies on MetaTrader5's own
     auto-connect (which attaches to any running terminal).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("godswill.market_data.mt5_discovery")

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# --------------------------------------------------------------------------- #
# Tier 1 — running terminal
# --------------------------------------------------------------------------- #

def _running_terminal_paths() -> list[Path]:
    if sys.platform != "win32":
        return []
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "(Get-Process -Name terminal64 -ErrorAction SilentlyContinue)"
                ".Path | Select-Object -Unique",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception as exc:
        logger.debug("Running-process discovery failed: %s", exc)
        return []

    paths: list[Path] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        p = Path(line)
        if p.exists() and p.name.lower() == "terminal64.exe":
            paths.append(p)
    return paths


# --------------------------------------------------------------------------- #
# Tier 2 — registry
# --------------------------------------------------------------------------- #

def _registry_terminal_paths() -> list[Path]:
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:
        return []

    roots = [
        (winreg.HKEY_CURRENT_USER, r"Software\MetaQuotes\Terminal"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\MetaQuotes\Terminal"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\MetaQuotes\Terminal"),
    ]

    paths: list[Path] = []
    for hkey, subkey in roots:
        try:
            with winreg.OpenKey(hkey, subkey) as key:
                i = 0
                while True:
                    try:
                        inst_name = winreg.EnumKey(key, i)
                        i += 1
                    except OSError:
                        break
                    inst_path = _read_install_path(winreg, key, inst_name)
                    if inst_path:
                        paths.append(inst_path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            logger.debug("Registry read failed at %s: %s", subkey, exc)
            continue
    return paths


def _read_install_path(winreg, parent_key, inst_name: str) -> Path | None:
    """A MetaQuotes terminal subkey may expose its install dir via several
    value names, or store the executable directly in the subkey name."""
    try:
        with winreg.OpenKey(parent_key, inst_name) as inst:
            for value_name in ("InstallPath", "Path", "ExePath"):
                try:
                    val, _ = winreg.QueryValueEx(inst, value_name)
                except FileNotFoundError:
                    continue
                if not val:
                    continue
                candidate = Path(val)
                exe = candidate / "terminal64.exe" if candidate.is_dir() else candidate
                if exe.exists() and exe.name.lower() == "terminal64.exe":
                    return exe
    except OSError:
        pass
    return None


# --------------------------------------------------------------------------- #
# Tier 3 — filesystem scan
# --------------------------------------------------------------------------- #

def _scan_common_dirs() -> list[Path]:
    roots: list[Path] = []
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        raw = os.environ.get(env)
        if raw:
            roots.append(Path(raw))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(Path(local) / "Programs")

    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        try:
            for entry in root.iterdir():
                if not entry.is_dir():
                    continue
                exe = entry / "terminal64.exe"
                if exe.exists():
                    found.append(exe)
        except PermissionError:
            continue
        except OSError as exc:
            logger.debug("Scan of %s failed: %s", root, exc)
    return found


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def discover_terminal_paths() -> list[Path]:
    """Return all discovered MT5 terminal executables, best candidate first.

    Priority: running terminal > registry > filesystem scan.
    Empty list means: nothing installed, or nothing running and not registered.
    In that case the caller should try MetaTrader5.initialize() with no path.
    """
    ordered = _running_terminal_paths() + _registry_terminal_paths() + _scan_common_dirs()

    seen: set[str] = set()
    result: list[Path] = []
    for p in ordered:
        key = str(p).lower()
        if key in seen or not p.exists():
            continue
        seen.add(key)
        result.append(p)
    return result


def best_terminal_path() -> Path | None:
    found = discover_terminal_paths()
    return found[0] if found else None