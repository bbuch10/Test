import copy

import pytest

from autobuy.config import ConfigError, parse_config

BASE = {
    "budget": {"max_total_spend": 500, "max_orders": 1},
    "products": [{
        "name": "thing",
        "url": "https://example.com/p",
        "max_price": 100,
        "price_selector": ".price",
        "in_stock_selector": "button.add",
        "checkout": [
            {"click": "button.add"},
            {"check_total": ".total"},
            {"place_order": "button.place"},
        ],
    }],
}


def cfg(**changes):
    raw = copy.deepcopy(BASE)
    for path, value in changes.items():
        target = raw
        *parents, leaf = path.split("__")
        for key in parents:
            target = target[int(key)] if key.isdigit() else target[key]
        target[leaf] = value
    return raw


def test_valid_config_defaults_to_dry_run():
    c = parse_config(cfg())
    assert c.dry_run is True
    assert c.products[0].max_total == 100


@pytest.mark.parametrize("changes, message", [
    ({"budget__max_total_spend": 0}, "max_total_spend"),
    ({"poll_interval_seconds": 5}, "poll_interval_seconds"),
    ({"products__0__max_total": 50}, "max_total must be >="),
    ({"products__0__checkout": [{"click": "x"}, {"place_order": "y"}]}, "check_total"),
    ({"products__0__checkout": [{"check_total": "x"}, {"click": "z"}, {"place_order": "y"}]}, "check_total"),
    ({"products__0__checkout": [{"check_total": "x"}]}, "place_order"),
    ({"products__0__checkout": [{"fill": {"selector": "x"}}, {"check_total": "x"}, {"place_order": "y"}]}, "value"),
    ({"products__0__checkout": [{"teleport": "x"}, {"check_total": "x"}, {"place_order": "y"}]}, "unknown kind"),
    ({"products": []}, "no products"),
])
def test_rejects_unsafe_or_broken_config(changes, message):
    with pytest.raises(ConfigError, match=message):
        parse_config(cfg(**changes))


def test_product_max_total_does_not_leak_into_budget():
    c = parse_config(cfg(products__0__max_total=150))
    assert c.max_total_spend == 500
    assert c.products[0].max_total == 150
