"""
llm_interface.py — Natural language interface for TradingBot using Anthropic tool calling.

The LLM parses user intent and maps it to structured tool calls.
A safety validation layer sits between every LLM tool-call response
and actual Binance API execution — the LLM decides *what* to do,
but this layer decides *whether it is safe* to do it.

Usage:
    python llm_interface.py
"""

from __future__ import annotations
import os
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

from bot import TradingBot
from models import OrderSide, PositionSide, TimeInForce
from logger import get_logger

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

log = get_logger("llm_interface")

# ── Safety configuration ───────────────────────────────────────────────────────
# These guards run on every tool call before anything reaches Binance.
MAX_SAFE_QUANTITY = Decimal("1.0")          # Block orders above this qty
ALLOWED_SYMBOLS   = {"BTCUSDT", "ETHUSDT", "BNBUSDT"}  # Testnet symbol whitelist

# ── Tool schemas — what the LLM sees ──────────────────────────────────────────
# These mirror the TradingBot methods exactly so the LLM maps intent correctly.

TOOLS = [
    {
        "name": "place_market_order",
        "description": (
            "Places a MARKET order on Binance Futures Testnet. "
            "Executes immediately at the current market price. "
            "Use when the user says 'buy/sell at market' or gives no specific price."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":   {"type": "string", "description": "Trading pair, e.g. BTCUSDT"},
                "side":     {"type": "string", "enum": ["BUY", "SELL"]},
                "quantity": {"type": "number", "description": "Order size in base asset units"},
            },
            "required": ["symbol", "side", "quantity"],
        },
    },
    {
        "name": "place_limit_order",
        "description": (
            "Places a LIMIT order on Binance Futures Testnet. "
            "Will only fill at the specified price or better. "
            "Use when the user gives a specific price target."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":   {"type": "string", "description": "Trading pair, e.g. BTCUSDT"},
                "side":     {"type": "string", "enum": ["BUY", "SELL"]},
                "quantity": {"type": "number", "description": "Order size in base asset units"},
                "price":    {"type": "number", "description": "Limit price — required for LIMIT orders"},
            },
            "required": ["symbol", "side", "quantity", "price"],
        },
    },
    {
        "name": "get_open_orders",
        "description": "Fetches all currently open (unfilled) orders, optionally filtered by symbol.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Optional — filter by trading pair"},
            },
            "required": [],
        },
    },
    {
        "name": "get_account_balance",
        "description": "Returns available wallet balance for all non-zero assets.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_price",
        "description": "Returns the current mark price for a symbol.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Trading pair, e.g. BTCUSDT"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "cancel_all_open_orders",
        "description": "Cancels ALL open orders for a given symbol. Irreversible — use with care.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Trading pair, e.g. BTCUSDT"},
            },
            "required": ["symbol"],
        },
    },
]

# ── Safety validation ──────────────────────────────────────────────────────────

class SafetyError(Exception):
    """Raised when a tool call fails safety checks — never reaches Binance."""
    pass


def validate_tool_call(tool_name: str, tool_input: dict) -> None:
    """
    Validates every LLM tool call before execution.

    Raises SafetyError with a descriptive message if the call is unsafe.
    The error message is fed back to the LLM so it can explain to the user.

    Checks:
    - Symbol is in the allowed whitelist
    - Order quantity does not exceed MAX_SAFE_QUANTITY
    - LIMIT orders have a price (schema enforces this, but we double-check)
    - Quantity is a valid positive number
    """
    symbol = tool_input.get("symbol", "").upper()
    if symbol and symbol not in ALLOWED_SYMBOLS:
        raise SafetyError(
            f"Symbol '{symbol}' is not in the allowed list: {ALLOWED_SYMBOLS}. "
            "Update ALLOWED_SYMBOLS in llm_interface.py to add new symbols."
        )

    if "quantity" in tool_input:
        try:
            qty = Decimal(str(tool_input["quantity"]))
        except InvalidOperation:
            raise SafetyError(f"Invalid quantity value: {tool_input['quantity']!r}")

        if qty <= 0:
            raise SafetyError(f"Quantity must be positive. Received: {qty}")

        if qty > MAX_SAFE_QUANTITY:
            raise SafetyError(
                f"Quantity {qty} exceeds safety limit of {MAX_SAFE_QUANTITY}. "
                "Update MAX_SAFE_QUANTITY in llm_interface.py to raise this limit."
            )

    # Belt-and-suspenders: LIMIT orders must have a price even though schema requires it
    if tool_name == "place_limit_order" and "price" not in tool_input:
        raise SafetyError(
            "LIMIT order is missing a price. "
            "Please specify a price, or use a MARKET order to execute at current price."
        )


# ── Tool execution ─────────────────────────────────────────────────────────────

def execute_tool(bot: TradingBot, tool_name: str, tool_input: dict) -> Any:
    """
    Executes a validated tool call on the TradingBot.
    All results are converted to JSON-serialisable dicts/strings.
    """
    log.info("Executing tool: %s  input=%s", tool_name, tool_input)

    if tool_name == "place_market_order":
        result = bot.place_market_order(
            symbol   = tool_input["symbol"].upper(),
            side     = OrderSide[tool_input["side"]],
            quantity = Decimal(str(tool_input["quantity"])),
        )
        return {"order_id": result.order_id, "status": result.status.value,
                "symbol": result.symbol, "side": tool_input["side"]}

    if tool_name == "place_limit_order":
        result = bot.place_limit_order(
            symbol   = tool_input["symbol"].upper(),
            side     = OrderSide[tool_input["side"]],
            quantity = Decimal(str(tool_input["quantity"])),
            price    = Decimal(str(tool_input["price"])),
        )
        return {"order_id": result.order_id, "status": result.status.value,
                "symbol": result.symbol, "price": str(tool_input["price"])}

    if tool_name == "get_open_orders":
        symbol = tool_input.get("symbol")
        orders = bot.get_open_orders(symbol.upper() if symbol else None)
        return {"open_orders": orders, "count": len(orders)}

    if tool_name == "get_account_balance":
        balances = bot.get_account_balance()
        return {asset: str(amount) for asset, amount in balances.items()}

    if tool_name == "get_price":
        price = bot.get_price(tool_input["symbol"].upper())
        return {"symbol": tool_input["symbol"].upper(), "mark_price": str(price)}

    if tool_name == "cancel_all_open_orders":
        result = bot.cancel_all_open_orders(tool_input["symbol"].upper())
        return {"cancelled": True, "symbol": tool_input["symbol"].upper(), "detail": result}

    raise ValueError(f"Unknown tool: {tool_name!r}")


# ── Main conversation loop ─────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a trading assistant for a Binance Futures Testnet bot.
You help users place orders, check balances, view positions, and manage open orders
using natural language. Always confirm order details before placing — state the
symbol, side, quantity, and price (if applicable) in your response.
This is a testnet environment — no real money is involved."""


def run() -> None:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    bot    = TradingBot()

    print("\n🤖  Binance Futures Assistant (type 'quit' to exit)\n")
    print("  Examples:")
    print("  → 'What is the current BTC price?'")
    print("  → 'Place a limit buy for 0.01 BTCUSDT at 60000'")
    print("  → 'Show my open orders for ETHUSDT'")
    print("  → 'What is my account balance?'\n")

    conversation: list[dict] = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if user_input.lower() in {"quit", "exit", "q"}:
            print("Goodbye.")
            break

        if not user_input:
            continue

        conversation.append({"role": "user", "content": user_input})

        # ── Agentic tool-use loop ──────────────────────────────────────────────
        # The LLM may call multiple tools before giving a final text response.
        # We loop until the stop reason is "end_turn" (no more tool calls).

        while True:
            response = client.messages.create(
                model      = "claude-sonnet-4-20250514",
                max_tokens = 1024,
                system     = SYSTEM_PROMPT,
                tools      = TOOLS,
                messages   = conversation,
            )

            # Collect tool-use blocks and any text blocks from this response
            tool_results = []
            assistant_text = ""

            for block in response.content:
                if block.type == "text":
                    assistant_text = block.text

                elif block.type == "tool_use":
                    tool_name  = block.name
                    tool_input = block.input
                    tool_id    = block.id

                    print(f"\n  [tool call] {tool_name}({json.dumps(tool_input)})")

                    # ── Safety gate ───────────────────────────────────────────
                    try:
                        validate_tool_call(tool_name, tool_input)
                        result = execute_tool(bot, tool_name, tool_input)
                        log.info("Tool result: %s", result)
                        tool_results.append({
                            "type":        "tool_result",
                            "tool_use_id": tool_id,
                            "content":     json.dumps(result),
                        })

                    except SafetyError as e:
                        # Safety block — feed the reason back to the LLM
                        log.warning("Safety block on %s: %s", tool_name, e)
                        print(f"  [safety block] {e}")
                        tool_results.append({
                            "type":        "tool_result",
                            "tool_use_id": tool_id,
                            "content":     f"BLOCKED BY SAFETY LAYER: {e}",
                            "is_error":    True,
                        })

                    except Exception as e:
                        log.error("Tool execution error: %s", e)
                        tool_results.append({
                            "type":        "tool_result",
                            "tool_use_id": tool_id,
                            "content":     f"Execution error: {e}",
                            "is_error":    True,
                        })

            # Append assistant turn to conversation history
            conversation.append({"role": "assistant", "content": response.content})

            # If there were tool calls, feed results back and loop again
            if tool_results:
                conversation.append({"role": "user", "content": tool_results})
                continue  # let the LLM process results and respond

            # No tool calls — LLM gave a final text response, exit the inner loop
            break

        print(f"\nAssistant: {assistant_text}\n")


if __name__ == "__main__":
    run()