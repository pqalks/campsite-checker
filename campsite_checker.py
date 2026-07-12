"""
Parks Canada Campsite Availability Checker
==========================================
Polls reservation.pc.gc.ca for Lake Louise Soft-sided Campground availability
and sends an SMS alert via Twilio when a site opens up.

Setup:
  pip install playwright twilio python-dotenv
  playwright install chromium

Create a .env file with:
  TWILIO_ACCOUNT_SID=your_account_sid
  TWILIO_AUTH_TOKEN=your_auth_token
  TWILIO_FROM=+1xxxxxxxxxx   # your Twilio number
  TWILIO_TO=+1xxxxxxxxxx     # your personal number

Run:
  python campsite_checker.py
"""

import asyncio
import os
import random
import time
from datetime import datetime

from dotenv import load_dotenv
from playwright.async_api import async_playwright
from twilio.rest import Client

load_dotenv()

# ── Configuration ────────────────────────────────────────────────────────────

CAMPGROUND_URL = "https://reservation.pc.gc.ca/camping/campgrounds/availability"

# Edit these to match your search
SEARCH_CONFIG = {
    "park":        "Banff National Park",
    "campground":  "Lake Louise Campground - Soft-sided",
    "checkin":     "2026-08-01",   # YYYY-MM-DD
    "checkout":    "2026-08-04",   # YYYY-MM-DD
    "party_size":  2,
}

# How often to check (seconds). Randomized ±30s to avoid bot detection.
POLL_INTERVAL_BASE = 300   # 5 minutes

# Twilio credentials from .env
TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM  = os.getenv("TWILIO_FROM")
TWILIO_TO    = os.getenv("TWILIO_TO")

# ── Alert ────────────────────────────────────────────────────────────────────

def send_sms(message: str):
    """Send an SMS alert via Twilio."""
    if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, TWILIO_TO]):
        print("⚠️  Twilio credentials missing — printing alert instead:")
        print(f"   ALERT: {message}")
        return
    try:
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(body=message, from_=TWILIO_FROM, to=TWILIO_TO)
        print(f"✅ SMS sent: {message}")
    except Exception as e:
        print(f"❌ SMS failed: {e}")

# ── Scraper ──────────────────────────────────────────────────────────────────

async def check_availability() -> bool | None:
    """
    Returns:
        True  — sites are available
        False — no availability
        None  — page load failed / bot check hit
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-CA",
        )
        page = await context.new_page()

        # Mask webdriver flag
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        try:
            print(f"[{now()}] Loading Parks Canada reservation page...")
            await page.goto(CAMPGROUND_URL, wait_until="networkidle", timeout=30_000)

            # ── Fill in the search form ──────────────────────────────────────
            # Parks Canada's form varies — adapt selectors if the site changes.

            # Park selector
            await page.select_option('select[name="park"], select[id*="park"]',
                                     label=SEARCH_CONFIG["park"])
            await page.wait_for_timeout(1000)

            # Campground selector
            await page.select_option('select[name="campground"], select[id*="campground"]',
                                     label=SEARCH_CONFIG["campground"])
            await page.wait_for_timeout(500)

            # Dates
            await page.fill('input[name="checkin"], input[id*="checkin"]',
                            SEARCH_CONFIG["checkin"])
            await page.fill('input[name="checkout"], input[id*="checkout"]',
                            SEARCH_CONFIG["checkout"])

            # Party size
            await page.fill('input[name="partySize"], input[id*="party"]',
                            str(SEARCH_CONFIG["party_size"]))

            # Submit
            await page.click('button[type="submit"], input[type="submit"]')
            await page.wait_for_load_state("networkidle", timeout=20_000)

            # ── Parse results ────────────────────────────────────────────────
            content = await page.content()

            # These phrases appear on the Parks Canada results page
            no_avail_phrases = [
                "no sites available",
                "no availability",
                "aucun emplacement disponible",
            ]
            avail_phrases = [
                "available",
                "book now",
                "select",
            ]

            content_lower = content.lower()

            if any(p in content_lower for p in no_avail_phrases):
                return False

            if any(p in content_lower for p in avail_phrases):
                return True

            # Couldn't parse — might be a bot check or page change
            print(f"[{now()}] ⚠️  Couldn't parse page — possible bot check or layout change.")
            return None

        except Exception as e:
            print(f"[{now()}] ❌ Error during check: {e}")
            return None
        finally:
            await browser.close()

# ── Helpers ──────────────────────────────────────────────────────────────────

def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def jitter(base: int, spread: int = 30) -> int:
    """Add random ±spread seconds to avoid predictable bot patterns."""
    return base + random.randint(-spread, spread)

# ── Main loop ────────────────────────────────────────────────────────────────

async def main():
    cfg = SEARCH_CONFIG

    # SINGLE_CHECK=true → run once and exit (used by GitHub Actions)
    # Otherwise → run forever in a loop (used by Railway / local)
    single_check = os.getenv("SINGLE_CHECK", "false").lower() == "true"

    print("=" * 60)
    print("  Parks Canada Campsite Availability Checker")
    print("=" * 60)
    print(f"  Campground : {cfg['campground']}")
    print(f"  Dates      : {cfg['checkin']} → {cfg['checkout']}")
    print(f"  Party size : {cfg['party_size']}")
    print(f"  Mode       : {'single check (GitHub Actions)' if single_check else f'poll every ~{POLL_INTERVAL_BASE // 60} min'}")
    print("=" * 60)

    consecutive_failures = 0

    while True:
        result = await check_availability()

        if result is True:
            message = (
                f"🏕️ CAMPSITE AVAILABLE! "
                f"{cfg['campground']} "
                f"{cfg['checkin']} → {cfg['checkout']} "
                f"— Book now: {CAMPGROUND_URL}"
            )
            print(f"\n[{now()}] ✅ {message}\n")
            send_sms(message)
            consecutive_failures = 0

        elif result is False:
            print(f"[{now()}] No availability.")
            consecutive_failures = 0

        else:
            consecutive_failures += 1
            print(f"[{now()}] Check failed ({consecutive_failures} in a row).")
            if consecutive_failures >= 5:
                send_sms(
                    "⚠️ Campsite checker has failed 5 times in a row. "
                    "Possible bot block — check the script."
                )
                consecutive_failures = 0

        # GitHub Actions: run once and exit — the scheduler calls us every 5 min
        if single_check:
            print(f"[{now()}] Single-check mode — done.")
            break

        # Server mode: wait then loop
        wait = jitter(POLL_INTERVAL_BASE)
        print(f"[{now()}] Checking again in {wait // 60}m {wait % 60}s...")
        await asyncio.sleep(wait)

if __name__ == "__main__":
    asyncio.run(main())
