import pytest

from autobuy.bot import parse_price
from autobuy.ledger import Ledger


@pytest.mark.parametrize("text, expected", [
    ("$1,299.99", 1299.99),
    ("Now: $42", 42.0),
    ("Total: USD 7.5", 7.5),
    ("Sold out", None),
    ("", None),
    (None, None),
])
def test_parse_price(text, expected):
    assert parse_price(text) == expected


def test_budget_and_order_limits(tmp_path):
    path = tmp_path / "orders.json"
    ledger = Ledger(path, max_total_spend=300, max_orders=2)
    assert ledger.can_afford(300)[0]
    assert not ledger.can_afford(300.01)[0]

    ledger.record("a", 200, "u", dry_run=True)   # dry runs never count
    assert ledger.spent == 0 and not ledger.already_bought("a")

    ledger.record("a", 200, "u", dry_run=False)
    assert ledger.already_bought("a")
    assert not ledger.can_afford(150)[0]

    # Survives a restart.
    reloaded = Ledger(path, max_total_spend=300, max_orders=2)
    assert reloaded.spent == 200
    reloaded.record("b", 50, "u", dry_run=False)
    ok, why = reloaded.can_afford(1)
    assert not ok and "order limit" in why
