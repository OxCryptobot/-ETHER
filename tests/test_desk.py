"""Paper desk. A decision never sends an order, and the ledger cannot go negative."""
from core.kernel.desk import apply, cycle, decide


def test_buy_only_when_price_rises_and_cash_covers_it() -> None:
    assert decide(101.0, 100.0, 1000.0, 0.0) == "buy"
    assert decide(100.1, 100.0, 1000.0, 0.0) == "hold"
    assert decide(101.0, 100.0, 1.0, 0.0) == "hold"


def test_sell_only_when_price_falls_and_coin_is_held() -> None:
    assert decide(99.0, 100.0, 0.0, 1.0) == "sell"
    assert decide(99.0, 100.0, 1000.0, 0.0) == "hold"


def test_apply_keeps_value_and_stays_solvent() -> None:
    cash, coin = apply(1000.0, 0.0, "buy", 100.0)
    assert cash == 975.0
    assert abs(coin - 0.25) < 1e-9
    assert cash + coin * 100.0 == 1000.0
    cash, coin = apply(cash, coin, "sell", 100.0)
    assert cash == 1000.0
    assert coin == 0.0


def test_cycle_is_paper_and_writes_the_ledger(tmp_path) -> None:
    row = cycle(tmp_path, price=100.0)
    assert row["ok"] is True
    assert row["orders_sent"] == 0
    assert row["paper"] is True
    assert row["action"] == "hold"
    nxt = cycle(tmp_path, price=101.0)
    assert nxt["action"] == "buy"
    assert nxt["cash"] == 975.0
    assert nxt["orders_sent"] == 0
    text = (tmp_path / "artifacts" / "desk.json").read_text(encoding="utf-8")
    assert '"orders_sent": 0' in text


def test_missing_price_does_not_trade(tmp_path) -> None:
    row = cycle(tmp_path, fetch=False)
    assert row["ok"] is False
    assert row["orders_sent"] == 0
    assert row["action"] == "hold"
