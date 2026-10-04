from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

PositiveDecimal = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]


class Action(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"
    CLOSE_ALL = "CLOSE_ALL"


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signal_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    timestamp: datetime
    symbol: str = Field(pattern=r"^[A-Z0-9]{5,20}$")
    action: Action
    strategy: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    timeframe: str = Field(min_length=1, max_length=10)
    price: PositiveDecimal
    stop_loss: PositiveDecimal | None = None
    take_profit: PositiveDecimal | None = None

    @model_validator(mode="after")
    def validate_entry(self) -> "Signal":
        if self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must include timezone")
        if self.action in (Action.LONG, Action.SHORT):
            if self.stop_loss is None:
                raise ValueError("entry requires stop_loss")
            long = self.action == Action.LONG
            if (long and self.stop_loss >= self.price) or (
                not long and self.stop_loss <= self.price
            ):
                raise ValueError("stop_loss is on the wrong side")
            if self.take_profit is not None and (
                (long and self.take_profit <= self.price)
                or (not long and self.take_profit >= self.price)
            ):
                raise ValueError("take_profit is on the wrong side")
        elif self.stop_loss is not None or self.take_profit is not None:
            raise ValueError("close signals must omit stop_loss and take_profit")
        return self


class WebhookSignal(Signal):
    secret: SecretStr | None = Field(default=None, exclude=True)


class PriceTick(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(pattern=r"^[A-Z0-9]{5,20}$")
    price: PositiveDecimal


class TradingControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class PositionView(BaseModel):
    symbol: str
    side: Literal["LONG", "SHORT"]
    entry: PositiveDecimal
    quantity: PositiveDecimal


class Position(PositionView):
    stop_loss: PositiveDecimal
    take_profit: PositiveDecimal
    entry_fee: Decimal
    strategy: str
    signal_id: str
