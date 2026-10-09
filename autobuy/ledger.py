"""Persistent record of orders, used to enforce the budget and avoid buying the same thing twice."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class Ledger:
    def __init__(self, path: str | Path, max_total_spend: float, max_orders: int):
        self.path = Path(path)
        self.max_total_spend = max_total_spend
        self.max_orders = max_orders
        self.orders: list[dict] = json.loads(self.path.read_text()) if self.path.exists() else []

    @property
    def spent(self) -> float:
        return sum(o["total"] for o in self.orders if not o.get("dry_run"))

    @property
    def real_orders(self) -> int:
        return sum(1 for o in self.orders if not o.get("dry_run"))

    def already_bought(self, product_name: str) -> bool:
        return any(o["product"] == product_name and not o.get("dry_run") for o in self.orders)

    def can_afford(self, amount: float) -> tuple[bool, str]:
        if self.real_orders >= self.max_orders:
            return False, f"order limit reached ({self.real_orders}/{self.max_orders})"
        if self.spent + amount > self.max_total_spend:
            return False, (f"would exceed budget: spent ${self.spent:.2f} + ${amount:.2f} "
                           f"> ${self.max_total_spend:.2f}")
        return True, ""

    def record(self, product_name: str, total: float, url: str, dry_run: bool) -> None:
        self.orders.append({
            "product": product_name,
            "total": round(total, 2),
            "url": url,
            "dry_run": dry_run,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        self.path.write_text(json.dumps(self.orders, indent=2))
