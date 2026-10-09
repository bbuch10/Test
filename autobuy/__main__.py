"""CLI: python -m autobuy {login,check,run} [-c config.yaml]"""
from __future__ import annotations

import argparse
import logging
import sys

from playwright.sync_api import sync_playwright

from .bot import Bot
from .config import ConfigError, load_config


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="autobuy", description=__doc__)
    ap.add_argument("command", choices=["login", "check", "run"], help=(
        "login: open the browser so you can sign in to each store (saved to the profile). "
        "check: one pass, report stock/price only, never buys. "
        "run: watch and buy."))
    ap.add_argument("-c", "--config", default="config.yaml")
    ap.add_argument("--once", action="store_true", help="with 'run': do a single pass and exit")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        cfg = load_config(args.config)
    except (OSError, ConfigError) as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            cfg.profile_dir, headless=cfg.headless and args.command != "login")
        try:
            if args.command == "login":
                for product in cfg.products:
                    context.new_page().goto(product.url)
                input("Sign in to each store in the browser window (with a saved card and address), "
                      "then press Enter here to save the session... ")
                return 0
            bot = Bot(cfg, context)
            if args.command == "check":
                bot.run_once(buy=False)
            elif args.once:
                bot.run_once()
            else:
                bot.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            context.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
