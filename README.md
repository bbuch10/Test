# autobuy

A personal bot that watches product pages and checks out automatically when an item is in stock at or under your price.

It drives a real Chrome window using a browser profile you've signed in to. The bot never sees or stores your store passwords or card numbers. It uses the address and saved card already on your store account.

> **Run it on your own computer**, not on a server. It needs your signed-in browser profile. Some stores' terms limit automated purchasing, so check the terms for each store you point it at.

## Safety limits

Every one of these limits is always on:

| Limit | What it does |
|---|---|
| `dry_run: true` (default) | Goes through the whole checkout and stops right before **Place order**. Saves a screenshot and sends you a notification. |
| `max_price` | Skips the item if the listed price is above this, or if the price can't be read. |
| `max_total` | Re-reads the **final checkout total** (tax and shipping included) right before placing the order. Aborts if it's over this. |
| `budget.max_total_spend` / `budget.max_orders` | Hard caps across all real orders, tracked in `orders.json`, so they survive restarts. |
| One buy per product | Once a product is ordered, it's never bought again. |
| Config validation | The bot refuses to start unless `check_total` is the step right before `place_order`. |
| Polling floor | Checks no more often than every 30 seconds. |

If anything fails during checkout, the bot stops, saves a screenshot to `screenshots/`, and notifies you.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp config.example.yaml config.yaml
```

1. **Add your products to `config.yaml`.** For each one you need the URL, your price caps, and CSS selectors. To find a selector, right-click the element in Chrome, choose **Inspect**, then **Copy > Copy selector**. You can also use Playwright text selectors such as `button:has-text('Add to cart')`.
2. **Sign in:** run `python -m autobuy login`. A browser opens each product's store. Sign in, make sure a default address and card are saved, then press Enter.
3. **Test your selectors:** run `python -m autobuy check`. It prints `in_stock` and `price` for each product and never buys. If the price shows `None`, fix `price_selector`.
4. **Do a dry run:** run `python -m autobuy run --once` with `dry_run: true`, ideally on something that's currently in stock. Look at the screenshot it saves in `screenshots/` to confirm it reached the final review page with the right total. Delete `orders.json` afterwards if you like (dry-run entries never count toward the budget).
5. **Go live:** set `dry_run: false` and run `python -m autobuy run`. It keeps watching until you press Ctrl+C.

### Phone notifications (optional)

Install the [ntfy](https://ntfy.sh) app, subscribe to a long random topic name, and put that name in `notify.ntfy_topic`. You'll get a push when it starts a checkout, places an order, or aborts one.

### Checkout steps

| Step | Example |
|---|---|
| `click` | `- click: "button.add-to-cart"` |
| `goto` | `- goto: "https://store.com/cart"` |
| `wait_for` | `- wait_for: "text=Review your order"` |
| `fill` | `- fill: {selector: "input[name=cvv]", value_env: "AUTOBUY_CVV"}` (reads the value from an environment variable, so secrets stay out of the file) |
| `select` | `- select: {selector: "select#qty", value: "1"}` |
| `check_total` | `- check_total: ".order-total"` (required; must come right before `place_order`) |
| `place_order` | `- place_order: "button#place-order"` (required; must be the last step; skipped in dry run) |

## Tests

```bash
pytest
```

The end-to-end tests drive the bot through a fake store in `tests/fake_store/` with headless Chromium. They cover a live buy, a dry run, a price that's too high, a total over the cap, a budget overrun, and an out-of-stock item. If your Chromium isn't the build Playwright expects, set `CHROMIUM_PATH=/path/to/chromium`.
