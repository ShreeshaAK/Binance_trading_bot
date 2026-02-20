"""
bot.py — High-level TradingBot service layer.
"""

from __future__ import annotations
from decimal import Decimal
from typing import Optional

from client import BinanceFuturesClient
from config import Config, config as _default_config
from logger import get_logger
from models import (
    OrderRequest, OrderResponse, OrderSide, OrderType,
    Position, PositionSide, TimeInForce,
)

log = get_logger("bot")


class TradingBot:
    def __init__(self, cfg: Config = _default_config) -> None:
        self._cfg = cfg
        self._client = BinanceFuturesClient(cfg)
        log.info("TradingBot initialised  symbol=%s", cfg.default_symbol)

    def place_order(self, request: OrderRequest) -> OrderResponse:
        request.validate()
        log.info("Placing %s %s %s qty=%s",
                 request.order_type.value, request.side.value,
                 request.symbol, request.quantity)
        raw = self._client.post("/order", data=request.to_api_params())
        order = OrderResponse.from_api(raw)
        log.info("Order accepted  id=%s  status=%s", order.order_id, order.status.value)
        return order

    def place_market_order(self, symbol: str, side: OrderSide, quantity: Decimal,
                           position_side=PositionSide.BOTH, reduce_only=False) -> OrderResponse:
        return self.place_order(OrderRequest(
            symbol=symbol, side=side, order_type=OrderType.MARKET,
            quantity=quantity, position_side=position_side, reduce_only=reduce_only))

    def place_limit_order(self, symbol: str, side: OrderSide, quantity: Decimal,
                          price: Decimal, time_in_force=TimeInForce.GTC,
                          position_side=PositionSide.BOTH, reduce_only=False) -> OrderResponse:
        return self.place_order(OrderRequest(
            symbol=symbol, side=side, order_type=OrderType.LIMIT,
            quantity=quantity, price=price, time_in_force=time_in_force,
            position_side=position_side, reduce_only=reduce_only))

    def place_stop_limit_order(self, symbol: str, side: OrderSide, quantity: Decimal,
                               stop_price: Decimal, price: Decimal,
                               time_in_force=TimeInForce.GTC,
                               position_side=PositionSide.BOTH,
                               reduce_only=False) -> OrderResponse:
        """
        Stop-Limit order — triggers at stop_price, places limit at price.
        Best for stop-losses where you want price certainty on the fill.
        """
        return self.place_order(OrderRequest(
            symbol=symbol, side=side, order_type=OrderType.STOP,
            quantity=quantity, price=price, stop_price=stop_price,
            time_in_force=time_in_force, position_side=position_side,
            reduce_only=reduce_only))

    def place_stop_market_order(self, symbol: str, side: OrderSide, quantity: Decimal,
                                stop_price: Decimal, position_side=PositionSide.BOTH,
                                close_position=False) -> OrderResponse:
        return self.place_order(OrderRequest(
            symbol=symbol, side=side, order_type=OrderType.STOP_MARKET,
            quantity=quantity, stop_price=stop_price,
            position_side=position_side, close_position=close_position))

    def place_take_profit_limit_order(self, symbol: str, side: OrderSide, quantity: Decimal,
                                      stop_price: Decimal, price: Decimal,
                                      time_in_force=TimeInForce.GTC,
                                      position_side=PositionSide.BOTH) -> OrderResponse:
        """Take-Profit-Limit — triggers at stop_price, places limit at price."""
        return self.place_order(OrderRequest(
            symbol=symbol, side=side, order_type=OrderType.TAKE_PROFIT,
            quantity=quantity, price=price, stop_price=stop_price,
            time_in_force=time_in_force, position_side=position_side))

    def get_order(self, symbol: str, order_id: int) -> OrderResponse:
        raw = self._client.get("/order",
                               params={"symbol": symbol.upper(), "orderId": order_id},
                               signed=True)
        return OrderResponse.from_api(raw)

    def get_open_orders(self, symbol: Optional[str] = None) -> list[dict]:
        params = {"symbol": symbol.upper()} if symbol else {}
        return self._client.get("/openOrders", params=params, signed=True)

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        return self._client.delete("/order",
                                   params={"symbol": symbol.upper(), "orderId": order_id})

    def cancel_all_open_orders(self, symbol: str) -> dict:
        return self._client.delete("/allOpenOrders",
                                   params={"symbol": symbol.upper()})

    def get_account_balance(self) -> dict[str, Decimal]:
        raw = self._client.get("/balance", signed=True, v2=True)
        return {r["asset"]: Decimal(r["availableBalance"])
                for r in raw if Decimal(r["balance"]) != 0}

    def get_positions(self, symbol: Optional[str] = None) -> list[Position]:
        params = {"symbol": symbol.upper()} if symbol else {}
        raw = self._client.get("/positionRisk", params=params, signed=True, v2=True)
        return [Position.from_api(p) for p in raw if Decimal(p["positionAmt"]) != 0]

    def get_price(self, symbol: str) -> Decimal:
        data = self._client.get("/premiumIndex", params={"symbol": symbol.upper()})
        return Decimal(data["markPrice"])

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        if not 1 <= leverage <= 125:
            raise ValueError("Leverage must be between 1 and 125.")
        return self._client.post("/leverage",
                                 data={"symbol": symbol.upper(), "leverage": leverage})
