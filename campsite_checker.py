"""
Parks Canada Campsite Availability Checker
==========================================
Uses Parks Canada's internal API directly — no browser, no scraping.
Much faster and more reliable than Playwright.

The mapId=-2147483646 is the Lake Louise Soft-sided Campground map ID,
discovered from the URL: reservation.pc.gc.ca/create-booking/results?mapId=-2147483646

Setup:
  pip install requests twilio python-dotenv

Create a .env file with:
  TWILIO_ACCOUNT_SID=your_account_sid
  TWILIO_AUTH_TOKEN=your_auth_token
  TWILIO_FROM=+1xxxxxxxxxx
  TWILIO_TO=+1xxxxxxxxxx
"""

import os
import random
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────

# mapId for Lake Louise Soft-sided Campground
# Source: reservation.pc.gc.ca/create-booking/results?mapId=-2147483646
MAP_ID = -2147483646

SEARCH_CONFIG = {
    "checkin":    "2026-08-07",   # YYYY-MM-DD
    "checkout":   "2026-08-08",   # YYYY-MM-DD
}

BOOKING_URL = f"https://reservation.pc.gc.ca/create-booking/results?mapId={MAP_ID}&searchTabGroupId=0&bookingCategoryId=0"

# How often to check in server mode (seconds)
POLL_INTERVAL_BASE = 300

# Twilio
TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM  = os.getenv("TWILIO_FROM")
TWILIO_TO    = os.getenv("TWILIO_TO")

# ── Alert ──────────────────────────────────────────────────────────────────────

def send_sms(message: str):
    if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, TWILIO_TO]):
        print(f"⚠️  Twilio not configured — would have sent: {message}")
        return
    try:
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(body=message, from_=TWILIO_FROM, to=TWILIO_TO)
        print(f"✅ SMS sent!")
    except Exception as e:
        print(f"❌ SMS failed: {e}")

# ── Checker ────────────────────────────────────────────────────────────────────

def check_availability() -> bool | None:
    """
    Calls Parks Canada's availability API directly.
    Returns True if available, False if not, None if check failed.
    """
    checkin  = SEARCH_CONFIG["checkin"]
    checkout = SEARCH_CONFIG["checkout"]

    # Parks Canada's internal availability API endpoint
    api_url = (
        f"https://reservation.pc.gc.ca/api/availability/map"
        f"?mapId={MAP_ID}"
        f"&bookingCategoryId=0"
        f"&startDate={checkin}"
        f"&endDate={checkout}"
        f"&lang=en-CA"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-CA,en;q=0.9",
        "Referer": "https://reservation.pc.gc.ca/",
        "Origin": "https://reservation.pc.gc.ca",
    }

    try:
        print(f"[{now()}] Checking Parks Canada API...")
        resp = requests.get(api_url, headers=headers, timeout=15)
        print(f"[{now()}] Response status: {resp.status_code}")

        if resp.status_code != 200:
            print(f"[{now()}] ⚠️  Unexpected status code: {resp.status_code}")
            print(f"[{now()}] Response: {resp.text[:300]}")
            return None

        data = resp.json()
        print(f"[{now()}] API response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        print(f"[{now()}] Full response (first 500 chars): {str(data)[:500]}")

        # Parks Canada API returns availability per resource (campsite)
        # Look for any site that is available
        if isinstance(data, list):
            available = [item for item in data if item.get("availability") == 1 or item.get("isAvailable") == True]
            print(f"[{now()}] Total sites: {len(data)}, Available: {len(available)}")
            return len(available) > 0

        if isinstance(data, dict):
            # mapAvailabilities: availability of the whole map
            # mapLinkAvailabilities: dict of sub-map IDs → list of availability codes
            #   1 = available, 0 = not available, 2 = partially available
            # resourceAvailabilities: individual campsite availability (empty if none bookable)

            map_avail = data.get("mapAvailabilities", [])
            link_avail = data.get("mapLinkAvailabilities", {})
            resource_avail = data.get("resourceAvailabilities", {})

            print(f"[{now()}] Map availability codes: {map_avail}")
            print(f"[{now()}] Sub-map availability: {link_avail}")
            print(f"[{now()}] Resource availability: {resource_avail}")

            # Check if any availability code is 1 (available) at any level
            map_has_avail = 1 in map_avail

            link_has_avail = any(
                1 in codes
                for codes in link_avail.values()
                if isinstance(codes, list)
            )

            resource_has_avail = any(
                1 in (codes if isinstance(codes, list) else [codes])
                for codes in resource_avail.values()
            )

            is_available = map_has_avail or link_has_avail or resource_has_avail
            print(f"[{now()}] Available: {is_available} (map={map_has_avail}, links={link_has_avail}, resources={resource_has_avail})")
            return is_available

        print(f"[{now()}] ⚠️  Unexpected response format: {type(data)}")
        return None

    except requests.exceptions.Timeout:
        print(f"[{now()}] ❌ Request timed out")
        return None
    except Exception as e:
        print(f"[{now()}] ❌ Error: {e}")
        return None

# ── Helpers ────────────────────────────────────────────────────────────────────

def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def jitter(base: int, spread: int = 30) -> int:
    return base + random.randint(-spread, spread)

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    cfg = SEARCH_CONFIG
    single_check = os.getenv("SINGLE_CHECK", "false").lower() == "true"

    print("=" * 60)
    print("  Parks Canada Campsite Availability Checker")
    print("=" * 60)
    print(f"  Campground : Lake Louise Soft-sided (mapId={MAP_ID})")
    print(f"  Dates      : {cfg['checkin']} → {cfg['checkout']}")
    print(f"  Mode       : {'single check (GitHub Actions)' if single_check else f'poll every ~{POLL_INTERVAL_BASE // 60} min'}")
    print("=" * 60)

    consecutive_failures = 0

    while True:
        result = check_availability()

        if result is True:
            message = (
                f"🏕️ CAMPSITE AVAILABLE! Lake Louise Soft-sided "
                f"{cfg['checkin']} → {cfg['checkout']} "
                f"— Book now: {BOOKING_URL}"
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
                send_sms("⚠️ Campsite checker failed 5x in a row — check the script.")
                consecutive_failures = 0

        if single_check:
            print(f"[{now()}] Single-check mode — done.")
            break

        wait = jitter(POLL_INTERVAL_BASE)
        print(f"[{now()}] Checking again in {wait // 60}m {wait % 60}s...")
        time.sleep(wait)

if __name__ == "__main__":
    main()
