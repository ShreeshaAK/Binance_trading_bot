"""
models.py — Typed, validated data models.
Adds STOP (Stop-Limit) and TAKE_PROFIT (Take-Profit-Limit) order types.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional


class OrderSide(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    MARKET             = "MARKET"
    LIMIT              = "LIMIT"
    STOP_MARKET        = "STOP_MARKET"
    STOP               = "STOP"                # Stop-Limit (NEW)
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TAKE_PROFIT        = "TAKE_PROFIT"         # Take-Profit-Limit (NEW)

class PositionSide(str, Enum):
    BOTH  = "BOTH"
    LONG  = "LONG"
    SHORT = "SHORT"

class TimeInForce(str, Enum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    GTX = "GTX"

class OrderStatus(str, Enum):
    NEW              = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED           = "FILLED"
    CANCELED         = "CANCELED"
    REJECTED         = "REJECTED"
    EXPIRED          = "EXPIRED"

_STOP_LIMIT_TYPES  = (OrderType.STOP, OrderType.TAKE_PROFIT)
_STOP_MARKET_TYPES = (OrderType.STOP_MARKET, OrderType.TAKE_PROFIT_MARKET)


@dataclass
class OrderRequest:
    symbol:         str
    side:           OrderSide
    order_type:     OrderType
    quantity:       Decimal
    price:          Optional[Decimal] = None
    stop_price:     Optional[Decimal] = None
    time_in_force:  TimeInForce       = TimeInForce.GTC
    position_side:  PositionSide      = PositionSide.BOTH
    reduce_only:    bool              = False
    close_position: bool              = False

    def validate(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("'symbol' must not be empty.")
        self.symbol = self.symbol.upper().strip()
        if self.quantity <= 0:
            raise ValueError(f"'quantity' must be > 0, got {self.quantity}.")
        if self.order_type == OrderType.LIMIT:
            if self.price is None:
                raise ValueError("LIMIT orders require a price.")
            if self.price <= 0:
                raise ValueError(f"'price' must be > 0.")
        if self.order_type in _STOP_MARKET_TYPES:
            if self.stop_price is None:
                raise ValueError(f"{self.order_type.value} requires a stop price.")
        if self.order_type in _STOP_LIMIT_TYPES:
            if self.stop_price is None:
                raise ValueError(f"Stop-Limit requires a stop (trigger) price.")
            if self.price is None:
                raise ValueError(f"Stop-Limit requires a limit price.")

    def to_api_params(self) -> dict:
        self.validate()
        params: dict = {
            "symbol":       self.symbol,
            "side":         self.side.value,
            "type":         self.order_type.value,
            "quantity":     str(self.quantity),
            "positionSide": self.position_side.value,
            "reduceOnly":   str(self.reduce_only).upper(),
        }
        if self.order_type == OrderType.LIMIT:
            params["price"]       = str(self.price)
            params["timeInForce"] = self.time_in_force.value
        if self.order_type in _STOP_LIMIT_TYPES:
            params["stopPrice"]   = str(self.stop_price)
            params["price"]       = str(self.price)
            params["timeInForce"] = self.time_in_force.value
        if self.order_type in _STOP_MARKET_TYPES:
            params["stopPrice"] = str(self.stop_price)
        if self.close_position:
            params["closePosition"] = "TRUE"
        return params

    def describe_type(self) -> str:
        labels = {
            OrderType.MARKET:             "Market",
            OrderType.LIMIT:              "Limit",
            OrderType.STOP_MARKET:        "Stop-Market",
            OrderType.STOP:               "Stop-Limit",
            OrderType.TAKE_PROFIT_MARKET: "Take-Profit Market",
            OrderType.TAKE_PROFIT:        "Take-Profit Limit",
        }
        return labels.get(self.order_type, self.order_type.value)


@dataclass
class OrderResponse:
    order_id:        int
    client_order_id: str
    symbol:          str
    status:          OrderStatus
    side:            OrderSide
    order_type:      OrderType
    orig_qty:        Decimal
    executed_qty:    Decimal
    avg_price:       Decimal
    price:           Decimal
    stop_price:      Decimal
    created_at:      datetime

    @classmethod
    def from_api(cls, data: dict) -> "OrderResponse":
        return cls(
            order_id        = int(data["orderId"]),
            client_order_id = data.get("clientOrderId", ""),
            symbol          = data["symbol"],
            status          = OrderStatus(data["status"]),
            side            = OrderSide(data["side"]),
            order_type      = OrderType(data["type"]),
            orig_qty        = Decimal(data.get("origQty",     "0") or "0"),
            executed_qty    = Decimal(data.get("executedQty", "0") or "0"),
            avg_price       = Decimal(data.get("avgPrice",    "0") or "0"),
            price           = Decimal(data.get("price",       "0") or "0"),
            stop_price      = Decimal(data.get("stopPrice",   "0") or "0"),
            created_at      = datetime.fromtimestamp(
                int(data.get("updateTime", data.get("time", 0))) / 1_000,
                tz=timezone.utc,
            ),
        )

    def __str__(self) -> str:
        return (
            f"#{self.order_id}  {self.symbol}  {self.side.value}  "
            f"{self.order_type.value}  qty={self.orig_qty}  "
            f"executed={self.executed_qty}  avgPrice={self.avg_price}  "
            f"status={self.status.value}"
        )


@dataclass
class Position:
    symbol:         str
    position_side:  PositionSide
    position_amt:   Decimal
    entry_price:    Decimal
    unrealized_pnl: Decimal
    leverage:       int
    isolated:       bool

    @classmethod
    def from_api(cls, data: dict) -> "Position":
        return cls(
            symbol         = data["symbol"],
            position_side  = PositionSide(data.get("positionSide", "BOTH")),
            position_amt   = Decimal(data["positionAmt"]),
            entry_price    = Decimal(data["entryPrice"]),
            unrealized_pnl = Decimal(data["unrealizedProfit"]),
            leverage       = int(data["leverage"]),
            isolated       = data.get("isolated", False),
        )

    @property
    def direction(self) -> str:
        if self.position_amt > 0: return "LONG"
        if self.position_amt < 0: return "SHORT"
        return "FLAT"

    @property
    def is_open(self) -> bool:
        return self.position_amt != Decimal("0")

    def __str__(self) -> str:
        return (
            f"{self.symbol}  {self.direction}  amt={abs(self.position_amt)}"
            f"  entry={self.entry_price}  uPnL={self.unrealized_pnl:+.4f}"
            f"  {self.leverage}x"
        )
