"""Stock/price checks and the scripted checkout, driven through a real (logged-in) browser profile."""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, TimeoutError as PWTimeout

from .config import Config, Product
from .ledger import Ledger
from .notify import notify

log = logging.getLogger(__name__)

PRICE_RE = re.compile(r"\d[\d,]*(?:\.\d{1,2})?")
STEP_TIMEOUT_MS = 15_000


def parse_price(text: str | None) -> float | None:
    """'$1,299.99' -> 1299.99. Returns None when no number is present."""
    if not text:
        return None
    m = PRICE_RE.search(text)
    return float(m.group().replace(",", "")) if m else None


@dataclass
class Status:
    in_stock: bool
    price: float | None


class CheckoutAborted(Exception):
    pass


class Bot:
    def __init__(self, cfg: Config, context: BrowserContext):
        self.cfg = cfg
        self.context = context
        self.ledger = Ledger(cfg.ledger_path, cfg.max_total_spend, cfg.max_orders)
        Path(cfg.screenshot_dir).mkdir(exist_ok=True)

    # ---- checking -------------------------------------------------------

    def check(self, page: Page, product: Product) -> Status:
        page.goto(product.url, wait_until="domcontentloaded")
        try:
            page.locator(product.in_stock_selector).first.wait_for(state="visible", timeout=5_000)
            in_stock = True
        except PWTimeout:
            in_stock = False
        price = None
        price_el = page.locator(product.price_selector).first
        if price_el.count():
            price = parse_price(price_el.inner_text())
        return Status(in_stock, price)

    def run_once(self, buy: bool = True) -> None:
        page = self.context.pages[0] if self.context.pages else self.context.new_page()
        for product in self.cfg.products:
            if not product.enabled:
                continue
            if buy and self.ledger.already_bought(product.name):
                log.info("[%s] already bought, skipping", product.name)
                continue
            try:
                status = self.check(page, product)
            except Exception as e:  # one broken page shouldn't stop the others
                log.warning("[%s] check failed: %s", product.name, e)
                continue
            log.info("[%s] in_stock=%s price=%s (max %.2f)",
                     product.name, status.in_stock, status.price, product.max_price)
            if not buy or not status.in_stock:
                continue
            if status.price is None:
                log.warning("[%s] in stock but price unreadable; not buying", product.name)
                continue
            if status.price > product.max_price:
                continue
            self.buy(page, product, status.price)

    def run_forever(self) -> None:
        mode = "DRY RUN" if self.cfg.dry_run else "LIVE"
        log.info("watching %d product(s) every %ss [%s]",
                 len(self.cfg.products), self.cfg.poll_interval_seconds, mode)
        while True:
            self.run_once()
            time.sleep(self.cfg.poll_interval_seconds)

    # ---- buying ---------------------------------------------------------

    def _screenshot(self, page: Page, product: Product, label: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe = re.sub(r"[^\w-]+", "_", product.name)
        path = str(Path(self.cfg.screenshot_dir) / f"{stamp}-{safe}-{label}.png")
        try:
            page.screenshot(path=path, full_page=True)
        except Exception:
            pass
        return path

    def buy(self, page: Page, product: Product, listed_price: float) -> None:
        ok, why = self.ledger.can_afford(listed_price)
        if not ok:
            notify(self.cfg.ntfy_topic, f"Skipped {product.name}", f"In stock at ${listed_price:.2f} but {why}")
            return
        notify(self.cfg.ntfy_topic, f"Buying {product.name}", f"In stock at ${listed_price:.2f}, starting checkout")
        try:
            self._run_checkout(page, product)
        except CheckoutAborted as e:
            shot = self._screenshot(page, product, "aborted")
            notify(self.cfg.ntfy_topic, f"Checkout aborted: {product.name}", f"{e} (screenshot: {shot})")
        except Exception as e:
            shot = self._screenshot(page, product, "error")
            notify(self.cfg.ntfy_topic, f"Checkout error: {product.name}", f"{e} (screenshot: {shot})")

    def _run_checkout(self, page: Page, product: Product) -> None:
        verified_total: float | None = None
        for step in product.checkout:
            kind, arg = next(iter(step.items()))
            log.info("[%s] step %s %s", product.name, kind, arg if kind != "fill" else arg.get("selector"))

            if kind == "goto":
                page.goto(arg, wait_until="domcontentloaded")
            elif kind == "click":
                page.locator(arg).first.click(timeout=STEP_TIMEOUT_MS)
            elif kind == "wait_for":
                page.locator(arg).first.wait_for(state="visible", timeout=STEP_TIMEOUT_MS)
            elif kind == "fill":
                value = os.environ.get(arg["value_env"], "") if "value_env" in arg else str(arg["value"])
                page.locator(arg["selector"]).first.fill(value, timeout=STEP_TIMEOUT_MS)
            elif kind == "select":
                page.locator(arg["selector"]).first.select_option(str(arg["value"]), timeout=STEP_TIMEOUT_MS)
            elif kind == "check_total":
                el = page.locator(arg).first
                el.wait_for(state="visible", timeout=STEP_TIMEOUT_MS)
                total = parse_price(el.inner_text())
                if total is None:
                    raise CheckoutAborted("could not read order total")
                if total > product.max_total:
                    raise CheckoutAborted(f"order total ${total:.2f} exceeds max_total ${product.max_total:.2f}")
                ok, why = self.ledger.can_afford(total)
                if not ok:
                    raise CheckoutAborted(why)
                verified_total = total
            elif kind == "place_order":
                if verified_total is None:
                    raise CheckoutAborted("reached place_order without a verified total")
                self._place_order(page, product, arg, verified_total)

    def _place_order(self, page: Page, product: Product, selector: str, total: float) -> None:
        if self.cfg.dry_run:
            shot = self._screenshot(page, product, "dryrun")
            self.ledger.record(product.name, total, product.url, dry_run=True)
            notify(self.cfg.ntfy_topic, f"[DRY RUN] Would buy {product.name}",
                   f"Total ${total:.2f}. Stopped before placing order. Screenshot: {shot}")
            return
        button = page.locator(selector).first
        button.wait_for(state="visible", timeout=STEP_TIMEOUT_MS)
        # Record before clicking: if anything fails after the click we must assume the
        # order went through, so it still counts against the budget and won't be retried.
        self.ledger.record(product.name, total, product.url, dry_run=False)
        button.click(timeout=STEP_TIMEOUT_MS)
        try:
            page.wait_for_load_state("networkidle", timeout=30_000)
        except PWTimeout:
            pass
        shot = self._screenshot(page, product, "ordered")
        notify(self.cfg.ntfy_topic, f"Ordered {product.name}",
               f"Placed order for ${total:.2f}. Check your email for confirmation. Screenshot: {shot}")
