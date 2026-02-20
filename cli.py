"""
cli.py — Argparse-powered command-line interface for the trading bot.

Every subcommand maps to exactly one high-level bot method.
Input validation (types, ranges, cross-field rules) happens in two passes:

  1. argparse type= / choices= — catches type errors immediately.
  2. models.OrderRequest.validate() — catches logical errors (e.g. LIMIT
     without --price) before any network call is made.

Usage examples
--------------
    # Market BUY
    python cli.py order --symbol BTCUSDT --side BUY --type MARKET --qty 0.001

    # Limit SELL
    python cli.py order --symbol ETHUSDT --side SELL --type LIMIT \\
                        --qty 0.05 --price 3200

    # Check balances
    python cli.py balance

    # List open orders
    python cli.py orders --symbol BTCUSDT

    # Cancel a specific order
    python cli.py cancel --symbol BTCUSDT --order-id 123456789

    # Cancel ALL open orders for a symbol
    python cli.py cancel --symbol BTCUSDT --all

    # Show open positions
    python cli.py positions

    # Set leverage
    python cli.py leverage --symbol BTCUSDT --leverage 20

    # Get mark price
    python cli.py price --symbol BTCUSDT
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from decimal import Decimal, InvalidOperation

from client import BinanceAPIError, NetworkError
from config import config
from logger import get_logger
from bot import TradingBot
from models import OrderRequest, OrderSide, OrderType, PositionSide, TimeInForce

log = get_logger("cli")

# ---------------------------------------------------------------------------
# ANSI helpers — gracefully degraded on Windows when colours aren't supported
# ---------------------------------------------------------------------------

def _ansi(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

def green(t: str)  -> str: return _ansi("32", t)
def red(t: str)    -> str: return _ansi("31", t)
def yellow(t: str) -> str: return _ansi("33", t)
def cyan(t: str)   -> str: return _ansi("36", t)
def bold(t: str)   -> str: return _ansi("1", t)
def dim(t: str)    -> str: return _ansi("2", t)


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------

_WIDTH = 62

def _rule(char: str = "─") -> str:
    return dim(char * _WIDTH)

def _header(title: str) -> None:
    print(_rule())
    print(bold(f"  {title}"))
    print(_rule())

def _field(label: str, value: str, colour_fn=None) -> None:
    v = colour_fn(value) if colour_fn else value
    print(f"  {dim(label + ':'):<28}{v}")

def _ok(msg: str) -> None:
    print(f"\n  {green('✓')} {bold(msg)}\n")

def _fail(msg: str) -> None:
    print(f"\n  {red('✗')} {bold(msg)}\n", file=sys.stderr)

def _warn(msg: str) -> None:
    print(f"  {yellow('!')} {msg}")


# ---------------------------------------------------------------------------
# Argparse type converters
# ---------------------------------------------------------------------------

def _decimal(value: str) -> Decimal:
    """Convert a CLI string to a Decimal; argparse calls this as type=."""
    try:
        d = Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"Not a valid number: {value!r}")
    if d <= 0:
        raise argparse.ArgumentTypeError(f"Value must be > 0, got: {value}")
    return d


def _positive_int(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Not a valid integer: {value!r}")
    if n <= 0:
        raise argparse.ArgumentTypeError(f"Value must be > 0, got: {value}")
    return n


def _leverage_int(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Not a valid integer: {value!r}")
    if not 1 <= n <= 125:
        raise argparse.ArgumentTypeError(f"Leverage must be 1–125, got: {value}")
    return n


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------

def cmd_order(args: argparse.Namespace, bot: TradingBot) -> int:
    """Place a MARKET or LIMIT order."""

    # ── Cross-field validation ───────────────────────────────────────────────
    order_type = OrderType(args.type.upper())
    if order_type == OrderType.LIMIT and args.price is None:
        _fail("LIMIT orders require --price.")
        return 2

    # ── Build request ────────────────────────────────────────────────────────
    request = OrderRequest(
        symbol        = args.symbol.upper(),
        side          = OrderSide(args.side.upper()),
        order_type    = order_type,
        quantity      = args.qty,
        price         = args.price,
        time_in_force = TimeInForce(args.tif.upper()) if args.tif else TimeInForce.GTC,
        position_side = PositionSide(args.position_side.upper()),
        reduce_only   = args.reduce_only,
    )

    try:
        request.validate()
    except ValueError as exc:
        _fail(f"Input validation error: {exc}")
        log.warning("Validation failed: %s", exc)
        return 2

    # ── Print request summary ────────────────────────────────────────────────
    side_col = green if request.side == OrderSide.BUY else red
    _header("Order Request")
    _field("Symbol",        request.symbol)
    _field("Side",          request.side.value,        side_col)
    _field("Type",          request.order_type.value,  cyan)
    _field("Quantity",      str(request.quantity))
    if request.price is not None:
        _field("Price",     str(request.price))
    _field("Time-in-Force", request.time_in_force.value)
    _field("Position Side", request.position_side.value)
    _field("Reduce Only",   str(request.reduce_only))
    print()

    # ── Submit ────────────────────────────────────────────────────────────────
    log.info("Submitting order: %s", request.summary())
    try:
        order = bot.place_order(request)
    except (BinanceAPIError, NetworkError, ValueError) as exc:
        _fail(f"Order failed: {exc}")
        log.error("Order submission error: %s", exc, exc_info=True)
        return 1

    # ── Print response ────────────────────────────────────────────────────────
    status_col = green if str(order.status.value) in ("FILLED", "NEW") else yellow
    _header("Order Response")
    _field("Order ID",       str(order.order_id),       bold)
    _field("Client Order ID",order.client_order_id)
    _field("Symbol",         order.symbol)
    _field("Side",           order.side.value,          side_col)
    _field("Type",           order.order_type.value,    cyan)
    _field("Status",         order.status.value,        status_col)
    _field("Original Qty",   str(order.orig_qty))
    _field("Executed Qty",   str(order.executed_qty))
    _field("Avg Price",      str(order.avg_price) if order.avg_price else "—")
    _field("Limit Price",    str(order.price)     if order.price     else "—")
    _field("Created (UTC)",  order.created_at.strftime("%Y-%m-%d %H:%M:%S"))
    print(_rule())
    _ok("Order placed successfully.")
    log.info("Order placed: %s", order)
    return 0


def cmd_balance(args: argparse.Namespace, bot: TradingBot) -> int:
    """Show available wallet balances."""
    try:
        balances = bot.get_account_balance()
    except (BinanceAPIError, NetworkError) as exc:
        _fail(f"Could not fetch balances: {exc}")
        log.error("%s", exc, exc_info=True)
        return 1

    _header("Account Balances")
    if not balances:
        _warn("No non-zero balances found.")
    for asset, amount in balances.items():
        _field(asset, f"{amount:.8f}")
    print(_rule())
    return 0


def cmd_positions(args: argparse.Namespace, bot: TradingBot) -> int:
    """Show open futures positions."""
    symbol = args.symbol.upper() if args.symbol else None
    try:
        positions = bot.get_positions(symbol)
    except (BinanceAPIError, NetworkError) as exc:
        _fail(f"Could not fetch positions: {exc}")
        log.error("%s", exc, exc_info=True)
        return 1

    title = f"Open Positions{f'  ({symbol})' if symbol else ''}"
    _header(title)
    if not positions:
        _warn("No open positions.")
    for pos in positions:
        dir_col = green if pos.direction == "LONG" else red
        pnl_col = green if pos.unrealized_pnl >= 0 else red
        _field("Symbol",         pos.symbol)
        _field("Direction",      pos.direction,                        dir_col)
        _field("Amount",         str(abs(pos.position_amt)))
        _field("Entry Price",    str(pos.entry_price))
        _field("Unrealized PnL", f"{pos.unrealized_pnl:+.4f} USDT",   pnl_col)
        _field("Leverage",       f"{pos.leverage}×")
        _field("Margin Mode",    "Isolated" if pos.isolated else "Cross")
        print(dim("  " + "·" * (_WIDTH - 2)))
    print(_rule())
    return 0


def cmd_orders(args: argparse.Namespace, bot: TradingBot) -> int:
    """List open orders for a symbol."""
    symbol = args.symbol.upper() if args.symbol else None
    try:
        orders = bot.get_open_orders(symbol)
    except (BinanceAPIError, NetworkError) as exc:
        _fail(f"Could not fetch open orders: {exc}")
        log.error("%s", exc, exc_info=True)
        return 1

    title = f"Open Orders{f'  ({symbol})' if symbol else ''}"
    _header(title)
    if not orders:
        _warn("No open orders.")
    for o in orders:
        side_col = green if o["side"] == "BUY" else red
        _field("Order ID",    str(o["orderId"]),   bold)
        _field("Symbol",      o["symbol"])
        _field("Side",        o["side"],           side_col)
        _field("Type",        o["type"],           cyan)
        _field("Orig Qty",    o["origQty"])
        _field("Price",       o["price"] if o.get("price") else "—")
        _field("Stop Price",  o["stopPrice"] if o.get("stopPrice") and o["stopPrice"] != "0" else "—")
        _field("Status",      o["status"])
        print(dim("  " + "·" * (_WIDTH - 2)))
    print(_rule())
    return 0


def cmd_cancel(args: argparse.Namespace, bot: TradingBot) -> int:
    """Cancel a specific order or all open orders for a symbol."""
    symbol = args.symbol.upper()

    if args.all:
        log.info("Cancelling all open orders for %s", symbol)
        try:
            result = bot.cancel_all_open_orders(symbol)
        except (BinanceAPIError, NetworkError) as exc:
            _fail(f"Cancel all failed: {exc}")
            log.error("%s", exc, exc_info=True)
            return 1
        _header(f"Cancel All Open Orders  ({symbol})")
        _field("Result", str(result))
        print(_rule())
        _ok(f"All open orders for {symbol} cancelled.")
        return 0

    if args.order_id is None:
        _fail("Provide --order-id <id> or use --all.")
        return 2

    log.info("Cancelling order #%s on %s", args.order_id, symbol)
    try:
        result = bot.cancel_order(symbol, args.order_id)
    except (BinanceAPIError, NetworkError) as exc:
        _fail(f"Cancel failed: {exc}")
        log.error("%s", exc, exc_info=True)
        return 1

    _header("Cancel Order")
    _field("Order ID", str(result.get("orderId", args.order_id)), bold)
    _field("Symbol",   result.get("symbol", symbol))
    _field("Status",   result.get("status", "CANCELED"), yellow)
    print(_rule())
    _ok("Order cancelled.")
    return 0


def cmd_price(args: argparse.Namespace, bot: TradingBot) -> int:
    """Fetch and display the current mark price."""
    symbol = args.symbol.upper()
    try:
        price = bot.get_price(symbol)
    except (BinanceAPIError, NetworkError) as exc:
        _fail(f"Could not fetch price: {exc}")
        log.error("%s", exc, exc_info=True)
        return 1
    _header(f"Mark Price  ({symbol})")
    _field(symbol, str(price), bold)
    print(_rule())
    return 0


def cmd_leverage(args: argparse.Namespace, bot: TradingBot) -> int:
    """Set leverage for a symbol."""
    symbol = args.symbol.upper()
    try:
        result = bot.set_leverage(symbol, args.leverage)
    except (BinanceAPIError, NetworkError, ValueError) as exc:
        _fail(f"Set leverage failed: {exc}")
        log.error("%s", exc, exc_info=True)
        return 1
    _header(f"Set Leverage  ({symbol})")
    _field("Symbol",   result.get("symbol", symbol))
    _field("Leverage", f"{result.get('leverage', args.leverage)}×", cyan)
    print(_rule())
    _ok("Leverage updated.")
    return 0


# ---------------------------------------------------------------------------
# Parser construction
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading_bot",
        description=textwrap.dedent("""\
            Binance Futures Testnet — Trading Bot CLI
            ─────────────────────────────────────────
            Place orders, inspect positions & balances,
            manage open orders, and more.

            Credentials are loaded from environment variables or a .env file:
              BINANCE_TESTNET_API_KEY
              BINANCE_TESTNET_API_SECRET
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version="trading_bot 2.0.0"
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ── order ────────────────────────────────────────────────────────────────
    p_order = sub.add_parser(
        "order",
        help="Place a MARKET or LIMIT order",
        description=textwrap.dedent("""\
            Place a new order on Binance Futures Testnet.

            Examples:
              Market BUY  0.001 BTC
                python cli.py order --symbol BTCUSDT --side BUY \\
                              --type MARKET --qty 0.001

              Limit SELL  0.05 ETH  @ 3200 USDT
                python cli.py order --symbol ETHUSDT --side SELL \\
                              --type LIMIT --qty 0.05 --price 3200
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_order.add_argument("--symbol", "-s",  required=True,
                         metavar="SYMBOL",
                         help="Trading pair, e.g. BTCUSDT")
    p_order.add_argument("--side",   "-d",  required=True,
                         choices=["BUY", "SELL", "buy", "sell"],
                         metavar="SIDE",
                         help="BUY or SELL")
    p_order.add_argument("--type",   "-t",  required=True,
                         choices=["MARKET", "LIMIT", "market", "limit"],
                         metavar="TYPE",
                         help="MARKET or LIMIT")
    p_order.add_argument("--qty",    "-q",  required=True,
                         type=_decimal, metavar="QTY",
                         help="Order quantity (must be > 0)")
    p_order.add_argument("--price",  "-p",
                         type=_decimal, default=None, metavar="PRICE",
                         help="Limit price (required for LIMIT orders)")
    p_order.add_argument("--tif",
                         choices=["GTC", "IOC", "FOK", "GTX"],
                         default="GTC", metavar="TIF",
                         help="Time-in-Force: GTC (default), IOC, FOK, GTX")
    p_order.add_argument("--position-side",
                         choices=["BOTH", "LONG", "SHORT"],
                         default="BOTH", metavar="POS_SIDE",
                         help="BOTH (one-way), LONG, SHORT (hedge mode). Default: BOTH")
    p_order.add_argument("--reduce-only", action="store_true",
                         help="Mark order as reduce-only")

    # ── balance ──────────────────────────────────────────────────────────────
    sub.add_parser(
        "balance",
        help="Show available wallet balances",
    )

    # ── positions ────────────────────────────────────────────────────────────
    p_pos = sub.add_parser(
        "positions",
        help="Show open futures positions",
    )
    p_pos.add_argument("--symbol", "-s", default=None,
                       metavar="SYMBOL",
                       help="Filter by symbol (optional)")

    # ── orders ───────────────────────────────────────────────────────────────
    p_orders = sub.add_parser(
        "orders",
        help="List open orders",
    )
    p_orders.add_argument("--symbol", "-s", default=None,
                          metavar="SYMBOL",
                          help="Filter by symbol (optional)")

    # ── cancel ───────────────────────────────────────────────────────────────
    p_cancel = sub.add_parser(
        "cancel",
        help="Cancel an order or all orders for a symbol",
        description=textwrap.dedent("""\
            Cancel a single order or all open orders for a symbol.

            Examples:
              Cancel order #12345 on BTCUSDT
                python cli.py cancel --symbol BTCUSDT --order-id 12345

              Cancel ALL open orders on BTCUSDT
                python cli.py cancel --symbol BTCUSDT --all
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_cancel.add_argument("--symbol", "-s", required=True,
                          metavar="SYMBOL",
                          help="Trading pair, e.g. BTCUSDT")
    p_cancel.add_argument("--order-id", "-i", type=_positive_int, default=None,
                          metavar="ORDER_ID",
                          help="Order ID to cancel")
    p_cancel.add_argument("--all", "-a", action="store_true",
                          help="Cancel ALL open orders for the symbol")

    # ── price ────────────────────────────────────────────────────────────────
    p_price = sub.add_parser(
        "price",
        help="Show the current mark price for a symbol",
    )
    p_price.add_argument("--symbol", "-s", required=True,
                         metavar="SYMBOL",
                         help="Trading pair, e.g. BTCUSDT")

    # ── leverage ─────────────────────────────────────────────────────────────
    p_lev = sub.add_parser(
        "leverage",
        help="Set leverage for a symbol (1–125)",
    )
    p_lev.add_argument("--symbol",   "-s", required=True,
                       metavar="SYMBOL",
                       help="Trading pair, e.g. BTCUSDT")
    p_lev.add_argument("--leverage", "-l", required=True,
                       type=_leverage_int, metavar="LEVERAGE",
                       help="Leverage multiplier (1–125)")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

HANDLERS = {
    "order":     cmd_order,
    "balance":   cmd_balance,
    "positions": cmd_positions,
    "orders":    cmd_orders,
    "cancel":    cmd_cancel,
    "price":     cmd_price,
    "leverage":  cmd_leverage,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # ── Credentials check ────────────────────────────────────────────────────
    try:
        config.validate()
    except ValueError as exc:
        _fail(str(exc))
        return 2

    # ── Initialise bot ────────────────────────────────────────────────────────
    bot = TradingBot(config)

    # ── Dispatch ─────────────────────────────────────────────────────────────
    handler = HANDLERS.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    return handler(args, bot)


if __name__ == "__main__":
    sys.exit(main())
