# Binance Futures Testnet — Trading Bot

A clean, production-structured Python trading bot for **Binance USDT-M Futures
Testnet** with a full-featured argparse CLI, typed models, structured logging,
comprehensive error handling, and a **natural language interface powered by
Anthropic tool calling**.

---

## Architecture

```
trading_bot/
│
├── config.py           ← Immutable Config dataclass; reads .env / env vars
├── logger.py           ← Two-channel logger: coloured console + rotating file
├── client.py           ← Signed HTTP layer (HMAC-SHA256, error/network exceptions)
├── models.py           ← Typed dataclasses for requests & responses + validation
├── bot.py              ← High-level TradingBot service (business logic only)
│
├── cli.py              ← argparse CLI — all user interaction lives here
├── main.py             ← Programmatic demo that calls cli.main()
├── llm_interface.py    ← Natural language interface via Anthropic tool calling
│
├── requirements.txt
├── .env.example
└── logs/               ← Auto-created; rotating log files land here
```

### Layer responsibilities

| Layer | Does | Does not |
|---|---|---|
| `config.py` | Load credentials, expose constants | Touch network |
| `logger.py` | Configure handlers once | Contain business logic |
| `client.py` | Sign + send HTTP, raise typed errors | Know about orders or positions |
| `models.py` | Validate input, serialise to API params, parse responses | Touch network |
| `bot.py` | Compose client calls into domain operations | Print to stdout |
| `cli.py` | Parse argv, print formatted output, call bot | Contain business logic |
| `llm_interface.py` | Parse natural language, validate tool calls, execute via bot | Contain trading logic |

---

## Quick Start

### 1. Get testnet credentials

1. Visit [testnet.binancefuture.com](https://testnet.binancefuture.com)
2. Register / log in → API Management → generate a key pair

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure credentials

```bash
cp .env.example .env
# open .env and fill in your keys
```

`.env` format:
```
BINANCE_TESTNET_API_KEY=your_key
BINANCE_TESTNET_API_SECRET=your_secret
ANTHROPIC_API_KEY=your_anthropic_key   # required for llm_interface.py
```

---

## CLI Reference

### order — Place a MARKET or LIMIT order

```bash
python cli.py order --symbol BTCUSDT --side BUY  --type MARKET --qty 0.001
python cli.py order --symbol ETHUSDT --side SELL --type LIMIT  --qty 0.05 --price 3200
python cli.py order --symbol BTCUSDT --side BUY  --type LIMIT  --qty 0.001 --price 90000 --tif IOC
```

Flags: `--symbol`, `--side` (BUY|SELL), `--type` (MARKET|LIMIT), `--qty`,
`--price` (required for LIMIT), `--tif` (GTC|IOC|FOK|GTX),
`--position-side` (BOTH|LONG|SHORT), `--reduce-only`

### balance — Show wallet balances
```bash
python cli.py balance
```

### positions — Show open positions
```bash
python cli.py positions
python cli.py positions --symbol BTCUSDT
```

### orders — List open orders
```bash
python cli.py orders --symbol BTCUSDT
```

### cancel — Cancel orders
```bash
python cli.py cancel --symbol BTCUSDT --order-id 3425621987
python cli.py cancel --symbol BTCUSDT --all
```

### price — Get mark price
```bash
python cli.py price --symbol BTCUSDT
```

### leverage — Set leverage (1-125)
```bash
python cli.py leverage --symbol BTCUSDT --leverage 20
```

---

## LLM Natural Language Interface

`llm_interface.py` wraps the TradingBot with an **Anthropic tool-calling** layer,
allowing natural language commands instead of CLI flags.

```bash
python llm_interface.py
```

```
🤖  Binance Futures Assistant (type 'quit' to exit)

You: What is the current BTC price?
  [tool call] get_price({"symbol": "BTCUSDT"})
Assistant: The current mark price for BTCUSDT is $67,423.50.

You: Place a limit buy for 0.01 BTCUSDT at 60000
  [tool call] place_limit_order({"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.01, "price": 60000})
Assistant: Limit BUY order placed — 0.01 BTCUSDT at $60,000. Order ID: 4829301.

You: buy 5 BTC at market
  [safety block] Quantity 5 exceeds safety limit of 1.0.
Assistant: That order was blocked by the safety layer — the quantity (5 BTC) exceeds
the configured limit of 1.0. Update MAX_SAFE_QUANTITY in llm_interface.py to raise this.
```

### How tool calling works

1. User sends a natural language message
2. The Anthropic API identifies the intent and selects the appropriate tool
3. **Safety validation runs before any Binance API call:**
   - Symbol must be in `ALLOWED_SYMBOLS` whitelist
   - Quantity must not exceed `MAX_SAFE_QUANTITY`
   - LIMIT orders must include a price
4. If validation passes, the tool executes via `TradingBot`
5. The result is fed back to the LLM, which formats a natural language response
6. Full conversation history is maintained for multi-turn context

### Defined tools

| Tool | Maps to |
|---|---|
| `place_market_order` | `bot.place_market_order()` |
| `place_limit_order` | `bot.place_limit_order()` |
| `get_open_orders` | `bot.get_open_orders()` |
| `get_account_balance` | `bot.get_account_balance()` |
| `get_price` | `bot.get_price()` |
| `cancel_all_open_orders` | `bot.cancel_all_open_orders()` |

### Safety configuration

Edit the constants at the top of `llm_interface.py`:

```python
MAX_SAFE_QUANTITY = Decimal("1.0")                       # Max order size
ALLOWED_SYMBOLS   = {"BTCUSDT", "ETHUSDT", "BNBUSDT"}   # Symbol whitelist
```

---

## Error Handling

| Situation | Exception | Example message |
|---|---|---|
| Bad input | `ValueError` / argparse error | LIMIT orders require --price |
| Binance API error | `BinanceAPIError(code, msg)` | [-2019] Margin insufficient |
| Network / timeout | `NetworkError` | Connection failed / timed out |
| LLM safety block | `SafetyError` | Quantity 5 exceeds safety limit of 1.0 |

Exit codes: 0 = success, 1 = API/network failure, 2 = input/validation error

---

## Logging

- **Console**: INFO and above, ANSI-coloured
- **File** (`logs/bot.log`): DEBUG and above, plain text, rotates at 5 MB

Every HTTP request, response body, and tool call is logged at DEBUG level.

---

## Library Usage

```python
from decimal import Decimal
from bot import TradingBot
from models import OrderSide

bot = TradingBot()
order = bot.place_market_order("BTCUSDT", OrderSide.BUY, Decimal("0.001"))
print(order.order_id, order.status)

order = bot.place_limit_order("ETHUSDT", OrderSide.SELL,
                               Decimal("0.05"), price=Decimal("3200"))

balances  = bot.get_account_balance()
positions = bot.get_positions("BTCUSDT")
price     = bot.get_price("BTCUSDT")
bot.cancel_all_open_orders("BTCUSDT")
```