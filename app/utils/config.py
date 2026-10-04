import os
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["PAPER", "TESTNET", "LIVE"] = "PAPER"
    symbol: str = "BTCUSDT"
    timeframe: str = "4H"
    leverage: int = Field(default=5, ge=1, le=125)
    risk_per_trade: Decimal = Field(default=Decimal("0.01"), gt=0, le=Decimal("0.1"))
    reward_risk_ratio: Decimal = Field(default=Decimal("1.5"), gt=0)
    max_open_positions: Literal[1] = 1
    max_notional: Decimal = Field(default=Decimal("10000"), gt=0)
    max_quantity: Decimal = Field(default=Decimal("1"), gt=0)
    margin_utilization: Decimal = Field(default=Decimal("0.9"), gt=0, le=1)
    paper_initial_balance: Decimal = Field(default=Decimal("1000"), gt=0)
    paper_fee_rate: Decimal = Field(default=Decimal("0.0005"), ge=0, le=Decimal("0.01"))
    paper_slippage_bps: Decimal = Field(default=Decimal("2"), ge=0, le=100)
    quantity_step: Decimal = Field(default=Decimal("0.001"), gt=0)
    price_tick: Decimal = Field(default=Decimal("0.1"), gt=0)
    min_quantity: Decimal = Field(default=Decimal("0.001"), gt=0)
    min_notional: Decimal = Field(default=Decimal("100"), gt=0)
    max_signal_age_seconds: int = Field(default=300, ge=1, le=3600)
    max_future_seconds: int = Field(default=30, ge=0, le=120)
    queue_limit: int = Field(default=1000, ge=1, le=10000)
    database_path: Path = Path("data/paper.sqlite3")
    log_path: Path = Path("logs/orders.jsonl")
    kill_switch_path: Path = Path("STOP_TRADING")
    trading_enabled: bool = True
    webhook_secret: SecretStr = SecretStr("")
    admin_token: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def finite_values(self) -> "Settings":
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, Decimal) and not value.is_finite():
                raise ValueError(f"{name} must be finite")
        return self


def load_settings() -> Settings:
    load_dotenv()
    path = Path(os.getenv("BOT_CONFIG", "config.yaml"))
    if not path.is_file():
        raise ValueError("BOT_CONFIG file does not exist")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("config must be a mapping")
    # Secrets can only come from the environment, never from YAML.
    if {"webhook_secret", "admin_token"} & data.keys():
        raise ValueError("tokens must use environment variables")
    data["mode"] = os.getenv("BOT_MODE", data.get("mode", "PAPER"))
    if "TRADING_ENABLED" in os.environ:
        value = os.environ["TRADING_ENABLED"].lower()
        if value not in ("true", "false"):
            raise ValueError("TRADING_ENABLED must be true or false")
        data["trading_enabled"] = value == "true"
    data["webhook_secret"] = os.getenv("WEBHOOK_SECRET", "")
    data["admin_token"] = os.getenv("ADMIN_TOKEN", "")
    return Settings.model_validate(data)


def check_runtime(settings: Settings) -> None:
    if settings.mode != "PAPER":
        raise ValueError("V1 runs PAPER only. TESTNET and LIVE execution are not enabled.")
    for secret in (settings.webhook_secret, settings.admin_token):
        if len(secret.get_secret_value()) < 32:
            raise ValueError(
                "WEBHOOK_SECRET and ADMIN_TOKEN must each contain at least 32 characters"
            )
    if settings.webhook_secret == settings.admin_token:
        raise ValueError("Use separate webhook and admin tokens")
