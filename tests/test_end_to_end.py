"""Drives the real bot against tests/fake_store in headless Chromium."""
import json
import os
from pathlib import Path

import pytest

pw_api = pytest.importorskip("playwright.sync_api")

from autobuy.bot import Bot
from autobuy.config import parse_config

STORE = Path(__file__).parent / "fake_store"


def make_cfg(tmp_path, *, dry_run, max_price=1100, max_total=1200, budget=2000, page="product.html"):
    return parse_config({
        "dry_run": dry_run,
        "budget": {"max_total_spend": budget, "max_orders": 1},
        "ledger_path": str(tmp_path / "orders.json"),
        "screenshot_dir": str(tmp_path / "shots"),
        "products": [{
            "name": "widget",
            "url": (STORE / page).as_uri(),
            "max_price": max_price,
            "max_total": max_total,
            "price_selector": ".price",
            "in_stock_selector": "button.add",
            "checkout": [
                {"click": "button.add"},
                {"wait_for": "text=Review your order"},
                {"fill": {"selector": "input[name='cvv']", "value_env": "AUTOBUY_TEST_CVV"}},
                {"check_total": ".total"},
                {"place_order": "button.place"},
            ],
        }],
    })


@pytest.fixture(scope="module")
def browser():
    with pw_api.sync_playwright() as pw:
        try:
            b = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        except Exception as e:
            pytest.skip(f"chromium unavailable: {e}")
        yield b
        b.close()


def run(browser, cfg):
    context = browser.new_context()
    page = context.new_page()
    bot = Bot(cfg, context)
    bot.run_once()
    body = page.inner_text("body")
    context.close()
    return bot, body


def orders(tmp_path):
    p = tmp_path / "orders.json"
    return json.loads(p.read_text()) if p.exists() else []


def test_live_purchase(browser, tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOBUY_TEST_CVV", "123")
    bot, body = run(browser, make_cfg(tmp_path, dry_run=False))
    assert "Order placed" in body
    assert len(orders(tmp_path)) == 1
    assert orders(tmp_path)[0]["total"] == 1133.99 and orders(tmp_path)[0]["dry_run"] is False

    # Second pass must not buy again.
    _, body = run(browser, make_cfg(tmp_path, dry_run=False))
    assert len(orders(tmp_path)) == 1


def test_dry_run_stops_before_placing(browser, tmp_path):
    _, body = run(browser, make_cfg(tmp_path, dry_run=True))
    assert "Order placed" not in body and "Place order" in body
    assert orders(tmp_path)[0]["dry_run"] is True
    assert list((tmp_path / "shots").glob("*dryrun.png"))


def test_listed_price_too_high_skips(browser, tmp_path):
    _, body = run(browser, make_cfg(tmp_path, dry_run=False, max_price=1000))
    assert orders(tmp_path) == [] and "Review your order" not in body


def test_total_over_max_total_aborts(browser, tmp_path):
    _, body = run(browser, make_cfg(tmp_path, dry_run=False, max_total=1100))
    assert orders(tmp_path) == [] and "Order placed" not in body
    assert list((tmp_path / "shots").glob("*aborted.png"))


def test_total_over_budget_aborts(browser, tmp_path):
    _, body = run(browser, make_cfg(tmp_path, dry_run=False, budget=1100))
    assert orders(tmp_path) == [] and "Order placed" not in body


def test_out_of_stock_does_nothing(browser, tmp_path):
    _, body = run(browser, make_cfg(tmp_path, dry_run=False, page="oos.html"))
    assert orders(tmp_path) == [] and "Sold out" in body
