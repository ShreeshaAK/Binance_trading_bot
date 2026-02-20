"""
main.py — Programmatic demo runner.

Calls the same ``cli.main()`` function that the CLI uses, so it exercises
every layer: argparse validation → OrderRequest → BinanceFuturesClient.

Run:
    python main.py

Or invoke each command directly:
    python cli.py order --symbol BTCUSDT --side BUY --type MARKET --qty 0.001
    python cli.py balance
    python cli.py positions
    python cli.py price --symbol BTCUSDT
"""

from __future__ import annotations

from cli import main

DEMO_COMMANDS: list[list[str]] = [
    # ── Check the mark price ──────────────────────────────────────────────
    ["price", "--symbol", "BTCUSDT"],
    # ── View balance ──────────────────────────────────────────────────────
    ["balance"],
    # ── Set leverage ──────────────────────────────────────────────────────
    ["leverage", "--symbol", "BTCUSDT", "--leverage", "10"],
    # ── Market BUY ───────────────────────────────────────────────────────
    ["order", "--symbol", "BTCUSDT", "--side", "BUY",
     "--type", "MARKET", "--qty", "0.001"],
    # ── Limit SELL (5 % above — unlikely to fill immediately) ────────────
    # Uncomment and replace <PRICE> with an actual price:
    # ["order", "--symbol", "BTCUSDT", "--side", "SELL",
    #  "--type", "LIMIT", "--qty", "0.001", "--price", "<PRICE>"],
    # ── Inspect open orders ───────────────────────────────────────────────
    ["orders", "--symbol", "BTCUSDT"],
    # ── Inspect positions ─────────────────────────────────────────────────
    ["positions", "--symbol", "BTCUSDT"],
]


def run_demo() -> None:
    print("\n" + "═" * 62)
    print("  Binance Futures Testnet — Trading Bot Demo")
    print("═" * 62 + "\n")

    for cmd_args in DEMO_COMMANDS:
        print(f"\n$ python cli.py {' '.join(cmd_args)}")
        rc = main(cmd_args)
        if rc != 0:
            print(f"  [exit code {rc}]")

    print("\n" + "═" * 62)
    print("  Demo finished.  See logs/bot.log for full detail.")
    print("═" * 62 + "\n")


if __name__ == "__main__":
    run_demo()
