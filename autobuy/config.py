"""Load and validate config.yaml."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

MIN_POLL_SECONDS = 30
STEP_KINDS = {"click", "goto", "fill", "select", "wait_for", "check_total", "place_order"}


class ConfigError(ValueError):
    pass


@dataclass
class Product:
    name: str
    url: str
    max_price: float
    price_selector: str
    in_stock_selector: str
    checkout: list[dict]
    max_total: float = 0.0  # cap on the final checkout total (tax + shipping included)
    enabled: bool = True


@dataclass
class Config:
    products: list[Product]
    poll_interval_seconds: int = 120
    dry_run: bool = True
    max_total_spend: float = 0.0
    max_orders: int = 1
    profile_dir: str = "browser-profile"
    headless: bool = False
    ntfy_topic: str = ""
    ledger_path: str = "orders.json"
    screenshot_dir: str = "screenshots"


def _validate_checkout(name: str, steps: list) -> list[dict]:
    if not isinstance(steps, list) or not steps:
        raise ConfigError(f"{name}: 'checkout' must be a non-empty list of steps")
    for i, step in enumerate(steps):
        if not isinstance(step, dict) or len(step) != 1:
            raise ConfigError(f"{name}: checkout step {i} must have exactly one key, got {step!r}")
        kind, arg = next(iter(step.items()))
        if kind not in STEP_KINDS:
            raise ConfigError(f"{name}: checkout step {i} has unknown kind {kind!r}")
        if kind in ("fill", "select"):
            if not isinstance(arg, dict) or "selector" not in arg or not ({"value", "value_env"} & arg.keys()):
                raise ConfigError(f"{name}: '{kind}' step {i} needs 'selector' and 'value' (or 'value_env')")
        elif not isinstance(arg, str) or not arg:
            raise ConfigError(f"{name}: '{kind}' step {i} needs a string argument")
    kinds = [next(iter(s)) for s in steps]
    if kinds.count("place_order") != 1 or kinds[-1] != "place_order":
        raise ConfigError(f"{name}: checkout must end with exactly one 'place_order' step")
    if len(kinds) < 2 or kinds[-2] != "check_total":
        # Never press "place order" without re-reading the real total first, and allow
        # nothing between the two steps that could change the cart.
        raise ConfigError(f"{name}: the step right before 'place_order' must be 'check_total'")
    return steps


def parse_config(raw: dict) -> Config:
    if not isinstance(raw, dict):
        raise ConfigError("config must be a YAML mapping")

    budget = raw.get("budget") or {}
    max_total_spend = float(budget.get("max_total_spend", 0))
    max_orders = int(budget.get("max_orders", 1))
    if max_total_spend <= 0:
        raise ConfigError("budget.max_total_spend must be set to a positive number")
    if max_orders <= 0:
        raise ConfigError("budget.max_orders must be at least 1")

    interval = int(raw.get("poll_interval_seconds", 120))
    if interval < MIN_POLL_SECONDS:
        raise ConfigError(f"poll_interval_seconds must be >= {MIN_POLL_SECONDS} (don't hammer the store)")

    products = []
    for p in raw.get("products") or []:
        name = p.get("name") or p.get("url", "<unnamed>")
        for key in ("url", "max_price", "price_selector", "in_stock_selector", "checkout"):
            if key not in p:
                raise ConfigError(f"{name}: missing '{key}'")
        max_price = float(p["max_price"])
        if max_price <= 0:
            raise ConfigError(f"{name}: max_price must be positive")
        max_total = float(p.get("max_total", max_price))
        if max_total < max_price:
            raise ConfigError(f"{name}: max_total must be >= max_price")
        products.append(Product(
            name=name,
            url=p["url"],
            max_price=max_price,
            price_selector=p["price_selector"],
            in_stock_selector=p["in_stock_selector"],
            checkout=_validate_checkout(name, p["checkout"]),
            max_total=max_total,
            enabled=bool(p.get("enabled", True)),
        ))
    if not products:
        raise ConfigError("no products configured")

    browser = raw.get("browser") or {}
    notify = raw.get("notify") or {}
    return Config(
        products=products,
        poll_interval_seconds=interval,
        dry_run=bool(raw.get("dry_run", True)),
        max_total_spend=max_total_spend,
        max_orders=max_orders,
        profile_dir=browser.get("profile_dir", "browser-profile"),
        headless=bool(browser.get("headless", False)),
        ntfy_topic=notify.get("ntfy_topic", "") or "",
        ledger_path=raw.get("ledger_path", "orders.json"),
        screenshot_dir=raw.get("screenshot_dir", "screenshots"),
    )


def load_config(path: str | Path) -> Config:
    with open(path) as f:
        return parse_config(yaml.safe_load(f))
