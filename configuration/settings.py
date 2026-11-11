"""Typed configuration loaded from YAML + environment overrides."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class AppSettings(BaseModel):
    name: str = "GODSWILL"
    environment: Literal["demo", "backtest", "live"] = "demo"
    data_dir: Path = Path("./data")
    log_level: str = "INFO"


class DatabaseSettings(BaseModel):
    path: Path = Path("./data/godswill.db")


class MT5Settings(BaseModel):
    terminal_path: str | None = None
    login: int | None = None
    password: str | None = None
    server: str | None = None
    timeout_ms: int = 60_000


class RiskSettings(BaseModel):
    risk_per_trade_pct: float = Field(0.5, gt=0, le=5)
    fixed_risk_amount: float | None = None  # <--- THE MISSING FIELD
    max_open_positions: int = Field(5, ge=1)
    max_daily_loss_pct: float = Field(2.0, gt=0)
    max_weekly_loss_pct: float = Field(5.0, gt=0)
    max_drawdown_pct: float = Field(15.0, gt=0)
    min_reward_risk: float = Field(1.5, ge=1.0)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GODSWILL_", env_nested_delimiter="__", extra="ignore"
    )

    app: AppSettings = AppSettings()
    database: DatabaseSettings = DatabaseSettings()
    mt5: MT5Settings = MT5Settings()
    risk: RiskSettings = RiskSettings()

    @classmethod
    def load(cls, config_path: Path | None = None) -> "Settings":
        """Load YAML (if present) then apply env overrides."""
        data: dict = {}
        if config_path and config_path.exists():
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return cls(**data)


def resolve_config_path(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        return explicit
    local = Path("configuration/config.yaml")
    if local.exists():
        return local
    example = Path("configuration/config.example.yaml")
    return example if example.exists() else None