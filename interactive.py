"""
interactive.py — Interactive terminal menu for the Binance Futures Testnet bot.

Pure stdlib. No extra installs required.

Run:
    python interactive.py
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal, InvalidOperation
from typing import Optional

from client import BinanceAPIError, NetworkError
from config import config
from logger import get_logger
from bot import TradingBot
from models import OrderRequest, OrderSide, OrderType, PositionSide, TimeInForce

log = get_logger("interactive")

# ── ANSI colours (enable on Windows 10+) ─────────────────────────────────────
if sys.platform == "win32":
    os.system("")

def _c(code: str, t: str) -> str: return f"\033[{code}m{t}\033[0m"
def green(t):    return _c("32", t)
def red(t):      return _c("31", t)
def yellow(t):   return _c("33", t)
def cyan(t):     return _c("36", t)
def bold(t):     return _c("1",  t)
def dim(t):      return _c("2",  t)
def inv(t):      return _c("7",  t)   # inverted (highlight)

W = 60

def rule(c="─"):  return dim(c * W)
def header(title: str, sub: str = "") -> None:
    print()
    print(rule("═"))
    print(inv(f"  {title:<{W-2}}"))
    if sub:
        print(dim(f"  {sub}"))
    print(rule("═"))
    print()

def section(t: str) -> None:
    print(rule())
    print(bold(f"  {t}"))
    print(rule())

def field(label: str, value: str, fn=None) -> None:
    v = fn(value) if fn else value
    print(f"  {dim(label + ':'):<28}{v}")

def ok(m):   print(f"\n  {green('✓')} {bold(m)}\n")
def err(m):  print(f"\n  {red('✗')} {bold(m)}\n")
def warn(m): print(f"  {yellow('!')} {m}")
def tip(m):  print(f"  {cyan('·')} {dim(m)}")

def clr(): os.system("cls" if sys.platform == "win32" else "clear")
def pause(): input(f"\n  {dim('Press Enter to go back...')}")


# ── Input helpers ─────────────────────────────────────────────────────────────

def ask(label: str, default: str = "", hint: str = "") -> str:
    """Prompt user for text input."""
    h = f" {dim('(' + hint + ')')}" if hint else ""
    d = f" {dim('[' + default + ']')}" if default else ""
    try:
        v = input(f"  {cyan('?')} {label}{h}{d}: ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        raise KeyboardInterrupt
    return v if v else default


def ask_decimal(label: str, default: str = "", hint: str = "") -> Decimal:
    """Prompt for a positive decimal number, re-ask on bad input."""
    while True:
        raw = ask(label, default, hint)
        if not raw:
            print(f"  {red('A value is required.')}")
            continue
        try:
            d = Decimal(raw)
            if d <= 0:
                print(f"  {red('Must be greater than zero.')}")
                continue
            return d
        except InvalidOperation:
            print(f"  {red(f'{raw!r} is not a valid number.')}")


def ask_int(label: str, lo: int, hi: int, default: int) -> int:
    """Prompt for an integer in [lo, hi]."""
    while True:
        raw = ask(label, str(default), f"{lo}–{hi}")
        try:
            n = int(raw)
            if lo <= n <= hi:
                return n
            print(f"  {red(f'Must be between {lo} and {hi}.')}")
        except ValueError:
            print(f"  {red(f'{raw!r} is not a valid integer.')}")


def ask_menu(title: str, options: list[tuple[str, str]], back: bool = True) -> str:
    """
    Numbered menu.  Returns the key of the chosen option.
    options = [(key, label), ...]
    """
    print(f"\n  {bold(title)}")
    print(f"  {rule()}")
    for i, (key, label) in enumerate(options, 1):
        print(f"  {cyan(str(i) + '.')}  {label}")
    if back:
        print(f"  {dim('0.')}  {dim('Back')}")
    print()
    valid = [str(i) for i in range(1, len(options) + 1)]
    if back:
        valid.append("0")
    while True:
        raw = ask("Choose").upper()
        # Accept number
        if raw in valid:
            idx = int(raw)
            return "BACK" if idx == 0 else options[idx - 1][0]
        # Accept direct key match
        match = [k for k, _ in options if k == raw or k.upper() == raw]
        if match:
            return match[0]
        print(f"  {red('Invalid choice. Enter a number from the list.')}")


def ask_confirm(msg: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = ask(msg, hint=hint).lower()
    if not raw or raw in ("y", "yes"):
        return True
    if raw in ("n", "no"):
        return False
    return default


# ── Screens ───────────────────────────────────────────────────────────────────

def screen_price(bot: TradingBot) -> None:
    clr()
    header("📈  Mark Price", "Live testnet price feed")
    symbol = ask("Symbol", "BTCUSDT", "e.g. BTCUSDT, ETHUSDT").upper()
    print()
    try:
        price = bot.get_price(symbol)
        section(f"Mark Price  ·  {symbol}")
        field(symbol, str(price), bold)
        print(rule())
        ok(f"{symbol} = {price} USDT")
    except (BinanceAPIError, NetworkError) as e:
        err(str(e))
        log.error("%s", e)
    pause()


def screen_balance(bot: TradingBot) -> None:
    clr()
    header("💰  Account Balance", "Testnet wallet balances")
    try:
        balances = bot.get_account_balance()
        section("Available Balances")
        if not balances:
            warn("No non-zero balances found.")
        else:
            for asset, amount in balances.items():
                field(asset, f"{amount:.6f}", green if asset == "USDT" else None)
        print(rule())
    except (BinanceAPIError, NetworkError) as e:
        err(str(e))
        log.error("%s", e)
    pause()


def screen_positions(bot: TradingBot) -> None:
    clr()
    header("📊  Open Positions", "Active futures positions")
    raw = ask("Filter by symbol", "", "leave blank for all")
    symbol = raw.upper().strip() or None
    print()
    try:
        positions = bot.get_positions(symbol)
        section(f"Open Positions{f'  ({symbol})' if symbol else '  (all)'}")
        if not positions:
            warn("No open positions.")
        for pos in positions:
            pnl_col = green if pos.unrealized_pnl >= 0 else red
            field("Symbol",         pos.symbol)
            field("Direction",      pos.direction, green if pos.direction == "LONG" else red)
            field("Size",           str(abs(pos.position_amt)))
            field("Entry Price",    str(pos.entry_price))
            field("Unrealised PnL", f"{pos.unrealized_pnl:+.4f} USDT", pnl_col)
            field("Leverage",       f"{pos.leverage}×")
            print(dim("  " + "·" * (W - 2)))
        print(rule())
    except (BinanceAPIError, NetworkError) as e:
        err(str(e))
        log.error("%s", e)
    pause()


def screen_open_orders(bot: TradingBot) -> None:
    clr()
    header("📋  Open Orders", "All pending orders")
    raw = ask("Filter by symbol", "", "leave blank for all")
    symbol = raw.upper().strip() or None
    print()
    try:
        orders = bot.get_open_orders(symbol)
        section(f"Open Orders{f'  ({symbol})' if symbol else '  (all)'}")
        if not orders:
            warn("No open orders.")
        for o in orders:
            side_col = green if o["side"] == "BUY" else red
            field("Order ID",   str(o["orderId"]), bold)
            field("Symbol",     o["symbol"])
            field("Side",       o["side"], side_col)
            field("Type",       o["type"], cyan)
            field("Qty",        o["origQty"])
            field("Price",      o["price"] if o.get("price") and o["price"] != "0" else "—")
            field("Stop Price", o["stopPrice"] if o.get("stopPrice") and o["stopPrice"] != "0" else "—")
            field("Status",     o["status"])
            print(dim("  " + "·" * (W - 2)))
        print(rule())
    except (BinanceAPIError, NetworkError) as e:
        err(str(e))
        log.error("%s", e)
    pause()


def screen_cancel(bot: TradingBot) -> None:
    clr()
    header("🗑️  Cancel Orders")
    choice = ask_menu("What to cancel?", [
        ("ONE",  "Cancel a specific order by ID"),
        ("ALL",  "Cancel ALL open orders for a symbol"),
    ])
    if choice == "BACK":
        return

    symbol = ask("Symbol", "BTCUSDT").upper()

    if choice == "ALL":
        print()
        warn(f"This will cancel ALL open orders for {bold(symbol)}.")
        if not ask_confirm("Are you sure?", default=False):
            warn("Cancelled.")
            pause()
            return
        try:
            bot.cancel_all_open_orders(symbol)
            ok(f"All open orders for {symbol} cancelled.")
        except (BinanceAPIError, NetworkError) as e:
            err(str(e))
        pause()
        return

    # Cancel single order
    raw_id = ask("Order ID")
    try:
        order_id = int(raw_id)
    except ValueError:
        err(f"Invalid order ID: {raw_id!r}")
        pause()
        return

    try:
        result = bot.cancel_order(symbol, order_id)
        section("Cancelled Order")
        field("Order ID", str(result.get("orderId", order_id)), bold)
        field("Symbol",   result.get("symbol", symbol))
        field("Status",   result.get("status", "CANCELED"), yellow)
        print(rule())
        ok("Order cancelled.")
    except (BinanceAPIError, NetworkError) as e:
        err(str(e))
    pause()


def screen_leverage(bot: TradingBot) -> None:
    clr()
    header("⚙️  Set Leverage")
    symbol   = ask("Symbol", "BTCUSDT").upper()
    leverage = ask_int("Leverage", 1, 125, 10)
    print()
    if not ask_confirm(f"Set {bold(str(leverage) + '×')} leverage on {bold(symbol)}?"):
        warn("No change made.")
        pause()
        return
    try:
        result = bot.set_leverage(symbol, leverage)
        section("Leverage Updated")
        field("Symbol",   result.get("symbol", symbol))
        field("Leverage", f"{result.get('leverage', leverage)}×", cyan)
        print(rule())
        ok("Leverage updated.")
    except (BinanceAPIError, NetworkError) as e:
        err(str(e))
    pause()


# ── Place Order screen (the big one) ─────────────────────────────────────────

ORDER_TYPES = [
    ("MARKET",             "Market          — fills instantly at current price"),
    ("LIMIT",              "Limit           — fills at your specified price or better"),
    ("STOP",               "Stop-Limit  ★   — triggers at stop price, then places limit"),
    ("STOP_MARKET",        "Stop-Market     — triggers at stop price, then market fills"),
    ("TAKE_PROFIT",        "TP-Limit    ★   — take-profit trigger + limit exit"),
    ("TAKE_PROFIT_MARKET", "TP-Market       — take-profit trigger + market exit"),
]

def _explain_stop_limit() -> None:
    print(f"\n  {cyan('Stop-Limit explained:')}")
    tip("You set TWO prices:")
    tip("  Stop Price  → when mark price hits this, order is activated")
    tip("  Limit Price → the limit order placed when stop triggers")
    tip("Use it when you want a guaranteed exit price (but risk non-fill)")
    print()

def screen_place_order(bot: TradingBot) -> None:
    clr()
    header("🚀  Place Order", "New futures order")

    # ── Symbol ────────────────────────────────────────────────────────────────
    symbol = ask("Symbol", "BTCUSDT", "e.g. BTCUSDT, ETHUSDT").upper()

    # ── Live price hint ───────────────────────────────────────────────────────
    try:
        price_now = bot.get_price(symbol)
        tip(f"Current mark price: {bold(str(price_now))} USDT")
    except Exception:
        price_now = None

    # ── Side ──────────────────────────────────────────────────────────────────
    side_key = ask_menu("Side", [("BUY", green("BUY")), ("SELL", red("SELL"))])
    if side_key == "BACK":
        return
    side = OrderSide(side_key)

    # ── Order type ────────────────────────────────────────────────────────────
    type_key = ask_menu("Order Type", ORDER_TYPES)
    if type_key == "BACK":
        return
    order_type = OrderType(type_key)

    # ── Explain Stop-Limit if chosen ──────────────────────────────────────────
    if order_type in (OrderType.STOP, OrderType.TAKE_PROFIT):
        _explain_stop_limit()

    # ── Quantity ──────────────────────────────────────────────────────────────
    quantity = ask_decimal("Quantity", hint="e.g. 0.001 for BTC")

    # ── Price fields ──────────────────────────────────────────────────────────
    price:      Optional[Decimal] = None
    stop_price: Optional[Decimal] = None

    if order_type == OrderType.LIMIT:
        price = ask_decimal("Limit Price", hint="the price you want to fill at")

    elif order_type in (OrderType.STOP_MARKET, OrderType.TAKE_PROFIT_MARKET):
        stop_price = ask_decimal("Stop (Trigger) Price",
                                 hint="mark price that activates this order")

    elif order_type in (OrderType.STOP, OrderType.TAKE_PROFIT):
        stop_price = ask_decimal("Stop (Trigger) Price",
                                 hint="mark price that activates the order")
        price      = ask_decimal("Limit Price",
                                 hint="limit price placed when trigger fires")

    # ── Time-in-Force (for limit-based orders) ────────────────────────────────
    tif = TimeInForce.GTC
    if order_type in (OrderType.LIMIT, OrderType.STOP, OrderType.TAKE_PROFIT):
        tif_key = ask_menu("Time-in-Force", [
            ("GTC", "GTC — Good Till Cancel  (default)"),
            ("IOC", "IOC — Immediate or Cancel"),
            ("FOK", "FOK — Fill or Kill"),
            ("GTX", "GTX — Post Only"),
        ])
        tif = TimeInForce(tif_key) if tif_key != "BACK" else TimeInForce.GTC

    # ── Build request ─────────────────────────────────────────────────────────
    request = OrderRequest(
        symbol=symbol, side=side, order_type=order_type,
        quantity=quantity, price=price, stop_price=stop_price,
        time_in_force=tif,
    )

    # ── Validate early ────────────────────────────────────────────────────────
    try:
        request.validate()
    except ValueError as e:
        err(f"Validation error: {e}")
        pause()
        return

    # ── Confirmation screen ───────────────────────────────────────────────────
    clr()
    header("🚀  Confirm Order", "Review before submitting")
    side_col = green if side == OrderSide.BUY else red

    section("Order Summary")
    field("Symbol",       symbol)
    field("Side",         side.value,                   side_col)
    field("Order Type",   request.describe_type(),      cyan)
    field("Quantity",     str(quantity))
    if stop_price:
        field("Stop Price",  str(stop_price), yellow)
    if price:
        field("Limit Price", str(price))
    if order_type in (OrderType.LIMIT, OrderType.STOP, OrderType.TAKE_PROFIT):
        field("Time-in-Force", tif.value)
    if price_now:
        field("Current Price", str(price_now), dim)
    print(rule())

    if not ask_confirm("Submit this order?", default=True):
        warn("Order not sent.")
        pause()
        return

    # ── Submit ────────────────────────────────────────────────────────────────
    print()
    try:
        order = bot.place_order(request)
    except (BinanceAPIError, NetworkError, ValueError) as e:
        err(f"Order failed: {e}")
        log.error("Order error: %s", e, exc_info=True)
        pause()
        return

    # ── Response ──────────────────────────────────────────────────────────────
    clr()
    header("✅  Order Placed!", "Confirmed by Binance Testnet")
    status_col = green if order.status.value in ("FILLED", "NEW") else yellow

    section("Order Response")
    field("Order ID",       str(order.order_id),   bold)
    field("Symbol",         order.symbol)
    field("Side",           order.side.value,       side_col)
    field("Type",           order.order_type.value, cyan)
    field("Status",         order.status.value,     status_col)
    field("Original Qty",   str(order.orig_qty))
    field("Executed Qty",   str(order.executed_qty))
    field("Avg Fill Price",
          str(order.avg_price) if order.avg_price else "—")
    if order.stop_price and order.stop_price > 0:
        field("Stop Price", str(order.stop_price), yellow)
    if order.price and order.price > 0:
        field("Limit Price", str(order.price))
    field("Created (UTC)",  order.created_at.strftime("%Y-%m-%d %H:%M:%S"))
    print(rule())
    ok("Order placed successfully.")
    log.info("Order placed: %s", order)
    pause()


# ── Main menu ─────────────────────────────────────────────────────────────────

MAIN_MENU = [
    ("ORDER",     "🚀  Place Order       Market / Limit / Stop-Limit"),
    ("PRICE",     "📈  Mark Price        Live price for any symbol"),
    ("BALANCE",   "💰  Account Balance   Testnet wallet"),
    ("POSITIONS", "📊  Open Positions    Active futures positions"),
    ("ORDERS",    "📋  Open Orders       Pending order list"),
    ("CANCEL",    "🗑️   Cancel Orders     Cancel one or all"),
    ("LEVERAGE",  "⚙️   Set Leverage      Change leverage (1–125)"),
    ("EXIT",      "🚪  Exit"),
]


def main() -> None:
    # Credentials check
    try:
        config.validate()
    except ValueError as e:
        print(f"\n{red('✗')} {e}\n")
        sys.exit(1)

    bot = TradingBot(config)

    while True:
        clr()
        header(
            "  Binance Futures Testnet — Trading Bot",
            "  Testnet only · No real money at risk"
        )
        choice = ask_menu("Main Menu", MAIN_MENU, back=False)

        handlers = {
            "ORDER":     screen_place_order,
            "PRICE":     screen_price,
            "BALANCE":   screen_balance,
            "POSITIONS": screen_positions,
            "ORDERS":    screen_open_orders,
            "CANCEL":    screen_cancel,
            "LEVERAGE":  screen_leverage,
        }

        if choice == "EXIT":
            clr()
            print(f"\n  {green('Goodbye!')}  All sessions logged to {dim('logs/bot.log')}\n")
            break

        handler = handlers.get(choice)
        if handler:
            try:
                handler(bot)
            except KeyboardInterrupt:
                pass   # Ctrl+C mid-prompt returns to main menu


if __name__ == "__main__":
    main()
