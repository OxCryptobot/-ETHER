"""Paper desk for the 1650. One decision per cycle. Never sends an order."""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

NOTIONAL = 25.0
CASH_FRACTION = 0.25
MOVE = 0.005


def quote(symbol: str = "BTC-USD", timeout: float = 3.0) -> Optional[float]:
    url = f"https://api.coinbase.com/v2/prices/{symbol}/spot"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
        return float(payload["data"]["amount"])
    except Exception:
        return None


def decide(price: float, prev: Optional[float], cash: float, coin: float) -> str:
    if price <= 0 or prev is None or prev <= 0:
        return "hold"
    change = (price - prev) / prev
    spend = min(NOTIONAL, cash * CASH_FRACTION)
    if change >= MOVE and spend >= 1.0:
        return "buy"
    held = coin * price
    if change <= -MOVE and held >= 1.0:
        return "sell"
    return "hold"


def apply(cash: float, coin: float, action: str, price: float) -> Tuple[float, float]:
    if price <= 0 or action == "hold":
        return cash, coin
    if action == "buy":
        spend = min(NOTIONAL, cash * CASH_FRACTION)
        if spend < 1.0:
            return cash, coin
        return cash - spend, coin + (spend / price)
    if action == "sell":
        held = coin * price
        take = min(NOTIONAL, held)
        if take < 1.0:
            return cash, coin
        return cash + take, coin - (take / price)
    return cash, coin


def _load(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"cash": 1000.0, "coin": 0.0, "prev": None}
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"cash": 1000.0, "coin": 0.0, "prev": None}
    return {
        "cash": float(row.get("cash") or 0.0),
        "coin": float(row.get("coin") or 0.0),
        "prev": row.get("prev"),
    }


def cycle(root: Path, price: Optional[float] = None, *, fetch: bool = True) -> Dict[str, Any]:
    root = Path(root)
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    ledger_path = art / "desk_ledger.json"
    state = _load(ledger_path)
    if price is None and fetch:
        price = quote()
    row: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "paper": True,
        "orders_sent": 0,
        "symbol": "BTC-USD",
    }
    if price is None or price <= 0:
        row.update({"ok": False, "action": "hold", "reason": "no_price"})
        (art / "desk.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        return row
    prev = float(state["prev"]) if state.get("prev") else None
    action = decide(price, prev, state["cash"], state["coin"])
    cash, coin = apply(state["cash"], state["coin"], action, price)
    if cash < -1e-6 or coin < -1e-6:
        action = "hold"
        cash, coin = state["cash"], state["coin"]
    equity = cash + coin * price
    ledger = {"cash": round(cash, 8), "coin": round(coin, 8), "prev": price, "equity": round(equity, 8)}
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    row.update({
        "ok": True,
        "action": action,
        "price": price,
        "cash": ledger["cash"],
        "coin": ledger["coin"],
        "equity": ledger["equity"],
    })
    (art / "desk.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row
