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
from datetime import datetime

from dotenv import load_dotenv
from playwright.async_api import async_playwright
from twilio.rest import Client

load_dotenv()

# ── Configuration ────────────────────────────────────────────────────────────

CAMPGROUND_URL = "https://reservation.pc.gc.ca/camping/campgrounds/availability"

# Edit these to match your search
SEARCH_CONFIG = {
    "park":        "Banff - Lake Louise",        # exactly as it appears in the dropdown
    "campground":  "Lake Louise Campground - Soft-sided",
    "checkin":     "2026-08-07",   # YYYY-MM-DD
    "checkout":    "2026-08-08",   # YYYY-MM-DD
    "party_size":  1,
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
            await page.goto(CAMPGROUND_URL, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(4000)  # let Angular fully render

            # ── Screenshot for debugging ──────────────────────────────────────
            await page.screenshot(path="debug_screenshot.png", full_page=False)
            print(f"[{now()}] Screenshot saved.")

            # ── Print page title and all buttons/inputs ───────────────────────
            title = await page.title()
            print(f"[{now()}] Page title: {title}")

            labels = await page.evaluate("""
                () => [...document.querySelectorAll('[aria-label], input, button, select')]
                    .map(el => el.tagName + ' id=' + el.id + ' aria-label=' + el.getAttribute('aria-label') + ' text=' + el.innerText?.slice(0,30))
                    .slice(0, 20)
            """)
            for l in labels:
                print(f"  {l}")

            # ── Dismiss cookie consent if present ────────────────────────────
            try:
                await page.click('button:has-text("I Consent")', timeout=5_000)
                print(f"[{now()}] Dismissed cookie consent.")
                await page.wait_for_timeout(3000)
            except Exception:
                print(f"[{now()}] No cookie banner found.")

            # ── Post-consent labels ───────────────────────────────────────────
            labels2 = await page.evaluate("""
                () => [...document.querySelectorAll('[aria-label], input, select')]
                    .map(el => el.tagName + ' id=' + el.id + ' aria-label=' + el.getAttribute('aria-label'))
                    .slice(0, 20)
            """)
            print(f"[{now()}] Post-consent elements:")
            for l in labels2:
                print(f"  {l}")

            # ── Park: Angular Material autocomplete ──────────────────────────
            print(f"[{now()}] Selecting park...")
            park_input = page.locator('[aria-label="Select park"], [role="combobox"][aria-label*="park" i], input[id*="park"]').first
            await park_input.wait_for(state="visible", timeout=15_000)
            await park_input.click()
            await park_input.fill(SEARCH_CONFIG["park"])
            await page.wait_for_timeout(1000)  # wait for autocomplete dropdown

            # Click the matching option in the dropdown
            option = page.locator(f'mat-option:has-text("{SEARCH_CONFIG["park"]}")')
            await option.first.click(timeout=10_000)
            await page.wait_for_timeout(1000)

            # ── Campground: similar autocomplete ─────────────────────────────
            print(f"[{now()}] Selecting campground...")
            campground_input = page.locator('[id*="campground"], [aria-label*="campground"], [aria-label*="Campground"]').first
            await campground_input.wait_for(timeout=10_000)
            await campground_input.click()
            await campground_input.fill(SEARCH_CONFIG["campground"][:20])  # type first 20 chars
            await page.wait_for_timeout(1000)

            option = page.locator(f'mat-option:has-text("Soft-sided")')
            await option.first.click(timeout=10_000)
            await page.wait_for_timeout(500)

            # ── Dates ─────────────────────────────────────────────────────────
            print(f"[{now()}] Filling dates...")
            # Try common date field selectors
            checkin = page.locator('[id*="checkin"], [id*="check-in"], [id*="arrival"], [placeholder*="arrival" i]').first
            await checkin.wait_for(timeout=10_000)
            await checkin.fill(SEARCH_CONFIG["checkin"])
            await page.wait_for_timeout(300)

            checkout = page.locator('[id*="checkout"], [id*="check-out"], [id*="departure"], [placeholder*="departure" i]').first
            await checkout.fill(SEARCH_CONFIG["checkout"])
            await page.wait_for_timeout(300)

            # ── Party size ────────────────────────────────────────────────────
            try:
                party = page.locator('[id*="party"], [id*="guest"], [aria-label*="party" i]').first
                await party.fill(str(SEARCH_CONFIG["party_size"]))
                await page.wait_for_timeout(300)
            except Exception:
                pass  # Party size may not be required

            # ── Submit ────────────────────────────────────────────────────────
            print(f"[{now()}] Submitting search...")
            await page.click('button[type="submit"], button:has-text("Search"), button:has-text("Check")')
            await page.wait_for_load_state("networkidle", timeout=20_000)

            # ── Parse results ─────────────────────────────────────────────────
            content = await page.content()
            content_lower = content.lower()

            no_avail_phrases = [
                "no sites available",
                "no availability",
                "aucun emplacement disponible",
                "no campsites",
                "0 available",
            ]
            avail_phrases = [
                "book now",
                "add to cart",
                "reserve",
                "sites available",
            ]

            if any(phrase in content_lower for phrase in no_avail_phrases):
                return False

            if any(phrase in content_lower for phrase in avail_phrases):
                return True

            print(f"[{now()}] ⚠️  Couldn't parse results page — possible bot check or layout change.")
            # Save page snapshot for debugging
            print(f"[{now()}] Page title: {await page.title()}")
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
